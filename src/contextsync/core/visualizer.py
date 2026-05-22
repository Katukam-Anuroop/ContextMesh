"""ContextSync Visualizer — Zero-server interactive graph visualization for codebase context."""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path
from typing import Any

from contextsync.config import ContextSyncConfig, find_config, load_config
from contextsync.core.dependency_graph import PythonDependencyExtractor
from contextsync.core.linter import ContextLinter
from contextsync.core.tree_walker import TreeWalker


class ContextVisualizer:
    """Compiles codebase context trees and dependency networks into a single static HTML page."""

    def __init__(self, repo_root: Path, config: ContextSyncConfig):
        self.repo_root = repo_root.resolve()
        self.config = config

    def generate_html(self) -> str:
        """Scan repository, construct network JSON, and inject into HTML template."""
        # 1. Run the linter to get real-time health metrics and stale flags
        linter = ContextLinter(self.repo_root, self.config)
        report = linter.run_scan()

        # Build lookup for issues by directory
        issues_by_dir: dict[str, list[dict[str, Any]]] = {}
        for issue in report.issues:
            # Map rule file to its directory
            rel_file = str(issue.file_path.relative_to(self.repo_root))
            dir_str = str(issue.file_path.parent.relative_to(self.repo_root))
            if dir_str == ".":
                dir_str = ""
            
            issue_dict = {
                "file": rel_file,
                "line": issue.line_number,
                "severity": issue.severity,
                "type": issue.issue_type,
                "message": issue.message,
                "context": issue.context,
            }
            issues_by_dir.setdefault(dir_str, []).append(issue_dict)

        # 2. Walk directories and build the graph
        walker = TreeWalker(self.repo_root, self.config)
        tree = walker.build_tree()

        # Extract code dependencies
        dep_extractor = PythonDependencyExtractor(self.repo_root)

        nodes = []
        edges = []
        node_id_map = {}
        idx = 1

        # Sort keys to ensure deterministic rendering
        for dir_path in sorted(tree.keys(), key=lambda p: str(p)):
            node = tree[dir_path]
            rel_dir = str(dir_path.relative_to(self.repo_root))
            if rel_dir == ".":
                rel_dir = ""

            node_id_map[dir_path] = idx
            
            # Basic stats about this directory
            code_files = []
            try:
                if dir_path.is_dir():
                    code_files = sorted([
                        f.name for f in dir_path.iterdir()
                        if f.is_file() and f.suffix.lower() in {
                            ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java"
                        }
                    ])
            except Exception:
                pass

            # Determine node health category
            node_issues = issues_by_dir.get(rel_dir, [])
            has_errors = any(i["severity"] == "error" for i in node_issues)
            has_warnings = any(i["severity"] == "warning" for i in node_issues)

            if has_errors:
                status = "error"
            elif has_warnings:
                status = "warning"
            elif node.exists:
                status = "healthy"
            else:
                status = "uncovered"

            # Determine group (based on top level directory)
            parts = Path(rel_dir).parts
            group = parts[0] if parts else "root"

            nodes.append({
                "id": idx,
                "label": rel_dir if rel_dir else "/",
                "path": rel_dir,
                "group": group,
                "has_context": node.exists,
                "status": status,
                "files": code_files,
                "files_count": len(code_files),
                "issues": node_issues,
                "content": node.content if node.exists else "",
            })
            idx += 1

        # 3. Add edges (Hierarchy & Lateral Dependencies)
        for dir_path, node in tree.items():
            current_id = node_id_map[dir_path]

            # A. Parent-child hierarchy edges
            if node.parent:
                parent_id = node_id_map.get(node.parent.dir_path)
                if parent_id:
                    edges.append({
                        "from": parent_id,
                        "to": current_id,
                        "type": "hierarchy",
                        "label": "parent-child",
                    })

            # B. Lateral links (declared in CONTEXT.md)
            for link in node.lateral_links:
                for other_path, other_id in node_id_map.items():
                    if other_path.name == link:
                        edges.append({
                            "from": current_id,
                            "to": other_id,
                            "type": "lateral",
                            "label": "lateral link",
                            "color": {"color": "#ec4899", "highlight": "#db2777"},  # Sleek magenta
                            "dashes": True,
                        })

            # C. AST resolved code dependencies
            try:
                ast_deps = dep_extractor.extract_dependencies(dir_path)
                for dep_path in ast_deps:
                    dep_id = node_id_map.get(dep_path)
                    if dep_id and dep_id != current_id:
                        edges.append({
                            "from": current_id,
                            "to": dep_id,
                            "type": "dependency",
                            "label": "imports code",
                            "color": {"color": "#6366f1", "highlight": "#4f46e5"},  # Indigo arrow
                        })
            except Exception:
                pass

        # 4. Global statistics
        stats = {
            "health_score": round(report.health_score, 1),
            "coverage_index": round(report.context_coverage_index, 1),
            "rules_count": report.total_rules,
            "stale_links": report.total_stale,
            "eligible_dirs": report.eligible_dirs,
            "covered_dirs": report.covered_dirs,
        }

        # 5. Build JSON payload
        payload = {
            "nodes": nodes,
            "edges": edges,
            "stats": stats,
            "repo_name": self.repo_root.name,
        }

        # 6. Inject into template
        html_content = HTML_TEMPLATE.replace("INSERT_PAYLOAD_HERE", json.dumps(payload, indent=2))
        return html_content

    def export_and_open(self, output_path: Path | None = None) -> Path:
        """Generate static HTML, save to .contextmesh/visualizer.html, and launch in browser."""
        if not output_path:
            output_dir = self.repo_root / ".contextsync"
            output_dir.mkdir(exist_ok=True)
            output_path = output_dir / "visualizer.html"

        html_content = self.generate_html()
        output_path.write_text(html_content, encoding="utf-8")
        
        # Open in default system browser
        webbrowser.open(output_path.as_uri())
        return output_path


# High-fidelity dashboard static template (Glassmorphic style)
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ContextSync Visualizer</title>
    
    <!-- Google Fonts & Vis.js -->
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <script src="https://unpkg.com/marked/marked.min.js"></script>
    
    <style>
        :root {
            --bg-base: #080c14;
            --bg-surface: rgba(13, 20, 35, 0.7);
            --bg-surface-hover: rgba(22, 32, 54, 0.85);
            --border-glow: rgba(99, 102, 241, 0.15);
            --border-subtle: rgba(255, 255, 255, 0.08);
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            
            --color-healthy: #10b981;
            --color-healthy-glow: rgba(16, 185, 129, 0.2);
            --color-uncovered: #f59e0b;
            --color-uncovered-glow: rgba(245, 158, 11, 0.2);
            --color-warning: #f97316;
            --color-warning-glow: rgba(249, 115, 22, 0.2);
            --color-error: #ef4444;
            --color-error-glow: rgba(239, 68, 68, 0.2);
            
            --font-main: 'Plus Jakarta Sans', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        body.light-theme {
            --bg-base: #f8fafc;
            --bg-surface: rgba(255, 255, 255, 0.8);
            --bg-surface-hover: rgba(241, 245, 249, 0.95);
            --border-glow: rgba(99, 102, 241, 0.1);
            --border-subtle: rgba(0, 0, 0, 0.06);
            --text-main: #0f172a;
            --text-muted: #64748b;
            --color-healthy-glow: rgba(16, 185, 129, 0.1);
            --color-uncovered-glow: rgba(245, 158, 11, 0.1);
            --color-warning-glow: rgba(249, 115, 22, 0.1);
            --color-error-glow: rgba(239, 68, 68, 0.1);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            transition: background-color 0.25s ease, border-color 0.25s ease;
        }

        body {
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: var(--font-main);
            height: 100vh;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        /* Glassmorphism Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1rem 2rem;
            background: var(--bg-surface);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-bottom: 1px solid var(--border-subtle);
            z-index: 10;
        }

        .logo-section {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .logo-icon {
            font-size: 1.5rem;
            animation: spin 8s linear infinite;
        }

        @keyframes spin {
            100% { transform: rotate(360deg); }
        }

        header h1 {
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: -0.025em;
            background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .action-bar {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .btn {
            background: var(--bg-surface-hover);
            border: 1px solid var(--border-subtle);
            color: var(--text-main);
            padding: 0.5rem 1rem;
            border-radius: 8px;
            font-family: var(--font-main);
            font-size: 0.875rem;
            font-weight: 600;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .btn:hover {
            border-color: #6366f1;
            box-shadow: 0 0 12px var(--border-glow);
        }

        /* Dashboard Grid Layout */
        .dashboard-container {
            display: grid;
            grid-template-columns: 360px 1fr 400px;
            flex: 1;
            overflow: hidden;
        }

        /* Panels (Sidebar & Detail Card) */
        .sidebar, .detail-panel {
            background: var(--bg-surface);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-right: 1px solid var(--border-subtle);
            overflow-y: auto;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .detail-panel {
            border-right: none;
            border-left: 1px solid var(--border-subtle);
        }

        /* Network Graph Canvas */
        .canvas-area {
            position: relative;
            background: radial-gradient(circle at center, rgba(99, 102, 241, 0.03) 0%, transparent 70%);
            overflow: hidden;
        }

        #network-canvas {
            width: 100%;
            height: 100%;
        }

        .canvas-controls {
            position: absolute;
            bottom: 1.5rem;
            left: 1.5rem;
            display: flex;
            gap: 0.5rem;
            z-index: 5;
        }

        /* Widgets & Cards */
        .section-title {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--text-muted);
            margin-bottom: 0.75rem;
            font-weight: 700;
        }

        .metrics-card {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }

        .metric-tile {
            background: var(--bg-surface-hover);
            border: 1px solid var(--border-subtle);
            padding: 1rem;
            border-radius: 12px;
            text-align: center;
        }

        .metric-value {
            font-size: 1.75rem;
            font-weight: 800;
            color: var(--text-main);
            margin-bottom: 0.25rem;
        }

        .metric-label {
            font-size: 0.75rem;
            color: var(--text-muted);
            font-weight: 500;
        }

        .gauge-section {
            background: var(--bg-surface-hover);
            border: 1px solid var(--border-subtle);
            border-radius: 16px;
            padding: 1.5rem;
            display: flex;
            align-items: center;
            gap: 1.5rem;
            position: relative;
            overflow: hidden;
        }

        .gauge-ring {
            width: 80px;
            height: 80px;
            transform: rotate(-90deg);
        }

        .gauge-circle-bg {
            fill: none;
            stroke: var(--border-subtle);
            stroke-width: 8;
        }

        .gauge-circle-val {
            fill: none;
            stroke: #6366f1;
            stroke-width: 8;
            stroke-dasharray: 226;
            stroke-dashoffset: 226;
            stroke-linecap: round;
            transition: stroke-dashoffset 1s ease-out;
        }

        .gauge-text {
            position: absolute;
            left: 1.5rem;
            width: 80px;
            text-align: center;
            font-size: 1.15rem;
            font-weight: 800;
        }

        /* Uncovered / Warnings List */
        .list-container {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
            max-height: 250px;
            overflow-y: auto;
        }

        .list-item {
            background: var(--bg-surface-hover);
            border: 1px solid var(--border-subtle);
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-size: 0.815rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            cursor: pointer;
        }

        .list-item:hover {
            border-color: #6366f1;
        }

        .badge-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }

        .bg-healthy { background-color: var(--color-healthy); box-shadow: 0 0 8px var(--color-healthy-glow); }
        .bg-uncovered { background-color: var(--color-uncovered); box-shadow: 0 0 8px var(--color-uncovered-glow); }
        .bg-warning { background-color: var(--color-warning); box-shadow: 0 0 8px var(--color-warning-glow); }
        .bg-error { background-color: var(--color-error); box-shadow: 0 0 8px var(--color-error-glow); }

        /* Detail Panel Card styling */
        .card-header {
            border-bottom: 1px solid var(--border-subtle);
            padding-bottom: 1rem;
        }

        .card-title {
            font-size: 1.15rem;
            font-weight: 700;
            word-break: break-all;
        }

        .card-meta {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 0.25rem;
        }

        .markdown-preview {
            background: var(--bg-surface-hover);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 1rem;
            font-size: 0.875rem;
            line-height: 1.5;
            overflow-y: auto;
            flex: 1;
            font-family: var(--font-main);
        }

        .markdown-preview h1, .markdown-preview h2, .markdown-preview h3 {
            margin-top: 1rem;
            margin-bottom: 0.5rem;
            font-weight: 700;
        }

        .markdown-preview h1 { font-size: 1.2rem; }
        .markdown-preview h2 { font-size: 1.05rem; }
        
        .markdown-preview p {
            margin-bottom: 0.75rem;
        }

        .markdown-preview code {
            font-family: var(--font-mono);
            background: rgba(99, 102, 241, 0.1);
            padding: 0.15rem 0.3rem;
            border-radius: 4px;
            font-size: 0.8rem;
        }

        .markdown-preview pre {
            background: rgba(0, 0, 0, 0.3);
            padding: 0.75rem;
            border-radius: 8px;
            overflow-x: auto;
            margin-bottom: 0.75rem;
        }

        .markdown-preview pre code {
            background: none;
            padding: 0;
        }

        .issues-container {
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }

        .issue-card {
            border-left: 3px solid;
            background: rgba(239, 68, 68, 0.05);
            padding: 0.75rem;
            border-radius: 4px;
            font-size: 0.815rem;
        }

        .issue-card.severity-error {
            border-left-color: var(--color-error);
            background: var(--color-error-glow);
        }

        .issue-card.severity-warning {
            border-left-color: var(--color-warning);
            background: var(--color-warning-glow);
        }

        .issue-snippet {
            font-family: var(--font-mono);
            background: rgba(0, 0, 0, 0.2);
            padding: 0.4rem;
            border-radius: 4px;
            margin-top: 0.4rem;
            font-size: 0.75rem;
        }

        /* SVG Modal */
        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(8px);
            z-index: 100;
            justify-content: center;
            align-items: center;
        }

        .modal-content {
            background: var(--bg-base);
            border: 1px solid var(--border-subtle);
            border-radius: 20px;
            padding: 2.5rem;
            width: 500px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
            position: relative;
        }

        .close-btn {
            position: absolute;
            top: 1rem;
            right: 1.5rem;
            font-size: 1.5rem;
            cursor: pointer;
            color: var(--text-muted);
        }

        .badge-preview-svg {
            margin: 1.5rem 0;
        }

        /* Scrollbar customizing */
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border-subtle); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #6366f1; }
    </style>
</head>
<body>

    <!-- Header Section -->
    <header>
        <div class="logo-section">
            <span class="logo-icon">🔄</span>
            <h1>ContextSync Visualizer <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 500;">(Local Graph)</span></h1>
        </div>
        <div class="action-bar">
            <button class="btn" id="badge-btn">⭐ Export README Badge</button>
            <button class="btn" id="theme-btn">🌓 Toggle Theme</button>
        </div>
    </header>

    <!-- Main Container -->
    <div class="dashboard-container">
        
        <!-- Left Sidebar: Diagnostics -->
        <div class="sidebar">
            
            <!-- Health Index Section -->
            <div>
                <h2 class="section-title">Context Health</h2>
                <div class="gauge-section">
                    <svg class="gauge-ring">
                        <circle class="gauge-circle-bg" cx="40" cy="40" r="36" />
                        <circle class="gauge-circle-val" id="health-ring" cx="40" cy="40" r="36" />
                    </svg>
                    <div class="gauge-text" id="health-value">0%</div>
                    <div>
                        <div style="font-size: 0.95rem; font-weight: 700;">Overall Health</div>
                        <div style="font-size: 0.75rem; color: var(--text-muted);" id="health-tier">Scanning...</div>
                    </div>
                </div>
            </div>

            <!-- Stats grid -->
            <div>
                <h2 class="section-title">Global Metrics</h2>
                <div class="metrics-card">
                    <div class="metric-tile">
                        <div class="metric-value" id="stat-coverage">0%</div>
                        <div class="metric-label">Directory CCI</div>
                    </div>
                    <div class="metric-tile">
                        <div class="metric-value" id="stat-rules">0</div>
                        <div class="metric-label">Active Rules</div>
                    </div>
                    <div class="metric-tile">
                        <div class="metric-value" id="stat-stale">0</div>
                        <div class="metric-label">Stale Refs</div>
                    </div>
                    <div class="metric-tile">
                        <div class="metric-value" id="stat-dirs">0</div>
                        <div class="metric-label">Folders</div>
                    </div>
                </div>
            </div>

            <!-- Folders List -->
            <div style="flex: 1; display: flex; flex-direction: column;">
                <h2 class="section-title">Module Status List</h2>
                <div class="list-container" id="module-list">
                    <!-- Dynamic List Items -->
                </div>
            </div>

        </div>

        <!-- Center: Interactive Graph -->
        <div class="canvas-area">
            <div id="network-canvas"></div>
            <div class="canvas-controls">
                <button class="btn" id="ctrl-zoom-in">➕</button>
                <button class="btn" id="ctrl-zoom-out">➖</button>
                <button class="btn" id="ctrl-fit">🔄 Fit</button>
                <button class="btn" id="ctrl-physics">⏸ Freeze</button>
            </div>
        </div>

        <!-- Right: Detail Panel -->
        <div class="detail-panel">
            <div class="card-header">
                <div class="card-title" id="detail-name">Select a node</div>
                <div class="card-meta" id="detail-meta">Click any directory module to view details</div>
            </div>

            <!-- File List -->
            <div id="detail-files-section" style="display: none;">
                <h2 class="section-title">Code Files</h2>
                <div class="list-container" id="detail-files" style="max-height: 120px;">
                    <!-- Code files inside module -->
                </div>
            </div>

            <!-- Context Code Review -->
            <div style="flex: 1; display: flex; flex-direction: column;" id="detail-content-section">
                <h2 class="section-title">CONTEXT.MD SUMMARY</h2>
                <div class="markdown-preview" id="detail-content">
                    *Select a module node to view context contents.*
                </div>
            </div>

            <!-- Active Issues -->
            <div id="detail-issues-section" style="display: none;">
                <h2 class="section-title">Diagnostic Warnings</h2>
                <div class="issues-container" id="detail-issues">
                    <!-- Issues list -->
                </div>
            </div>
        </div>

    </div>

    <!-- Badge Downloader Modal -->
    <div class="modal" id="badge-modal">
        <div class="modal-content">
            <span class="close-btn" id="close-modal-btn">&times;</span>
            <h2 style="font-size: 1.25rem; font-weight: 700; margin-bottom: 0.5rem;">🎉 Dynamic README Badge</h2>
            <p style="font-size: 0.875rem; color: var(--text-muted);">
                Showcase your codebase's context sanity with a gorgeous SVG badge in your GitHub README!
            </p>
            <div class="badge-preview-svg" id="badge-preview-container">
                <!-- SVG Code preview -->
            </div>
            <button class="btn" id="download-badge-btn" style="margin: 0 auto; background: #6366f1; border-color: #6366f1; color: white;">
                Download SVG Badge
            </button>
        </div>
    </div>

    <!-- Inject Payload -->
    <script>
        const data = INSERT_PAYLOAD_HERE;
    </script>

    <!-- App Logic -->
    <script>
        // Set document details
        document.title = `${data.repo_name} — ContextSync Visualizer`;

        // Render Sidebar Statistics
        const stats = data.stats;
        document.getElementById('health-value').innerText = `${stats.health_score}%`;
        document.getElementById('stat-coverage').innerText = `${stats.coverage_index}%`;
        document.getElementById('stat-rules').innerText = stats.rules_count;
        document.getElementById('stat-stale').innerText = stats.stale_links;
        document.getElementById('stat-dirs').innerText = stats.eligible_dirs;

        // Circular Gauge fill
        const circumference = 2 * Math.PI * 36;
        const strokeOffset = circumference - (stats.health_score / 100) * circumference;
        const ring = document.getElementById('health-ring');
        ring.style.strokeDashoffset = strokeOffset;

        // Set colors for Ring Gauge based on health
        let healthColor = '#10b981';
        let healthTier = 'EXCELLENT';
        if (stats.health_score < 50) {
            healthColor = '#ef4444';
            healthTier = 'CRITICAL DRIFT';
        } else if (stats.health_score < 75) {
            healthColor = '#f97316';
            healthTier = 'WARNING';
        } else if (stats.health_score < 90) {
            healthColor = '#f59e0b';
            healthTier = 'STABLE';
        }
        ring.style.stroke = healthColor;
        document.getElementById('health-tier').innerText = healthTier;
        document.getElementById('health-tier').style.color = healthColor;

        // Build list of modules in sidebar
        const moduleListContainer = document.getElementById('module-list');
        data.nodes.forEach(node => {
            const item = document.createElement('div');
            item.className = 'list-item';
            
            let statusDot = 'bg-uncovered';
            if (node.status === 'healthy') statusDot = 'bg-healthy';
            if (node.status === 'warning') statusDot = 'bg-warning';
            if (node.status === 'error') statusDot = 'bg-error';

            item.innerHTML = `
                <span>${node.label}</span>
                <span class="badge-dot ${statusDot}"></span>
            `;
            item.onclick = () => {
                selectNodeById(node.id);
            };
            moduleListContainer.appendChild(item);
        });

        // Initialize Vis.js Network Graph
        const container = document.getElementById('network-canvas');
        
        // Define nodes with styled colors
        const networkNodes = new vis.DataSet(data.nodes.map(node => {
            let color = {
                background: '#1e293b',
                border: '#475569',
                highlight: { background: '#334155', border: '#6366f1' }
            };

            if (node.status === 'healthy') {
                color = { background: '#064e3b', border: '#059669', highlight: { background: '#022c22', border: '#10b981' } };
            } else if (node.status === 'uncovered') {
                color = { background: '#451a03', border: '#d97706', highlight: { background: '#2d0f02', border: '#f59e0b' } };
            } else if (node.status === 'warning') {
                color = { background: '#431407', border: '#ea580c', highlight: { background: '#2c0d05', border: '#f97316' } };
            } else if (node.status === 'error') {
                color = { background: '#450a0a', border: '#dc2626', highlight: { background: '#2d0606', border: '#ef4444' } };
            }

            return {
                id: node.id,
                label: node.label === '/' ? '/' : node.label.split('/').pop(),
                title: node.path ? node.path : '/',
                color: color,
                shape: 'dot',
                size: 15 + Math.min(node.files_count * 2, 20), // Scale node size by code files count
                font: { color: 'var(--text-main)', size: 12, face: 'Plus Jakarta Sans', strokeWidth: 0 }
            };
        }));

        const networkEdges = new vis.DataSet(data.edges);

        const graphData = {
            nodes: networkNodes,
            edges: networkEdges
        };

        const options = {
            nodes: {
                borderWidth: 2,
                shadow: true
            },
            edges: {
                width: 2,
                arrows: {
                    to: { enabled: true, scaleFactor: 0.5 }
                },
                shadow: true,
                smooth: {
                    type: 'cubicBezier',
                    forceDirection: 'vertical',
                    roundness: 0.4
                }
            },
            groups: {
                useDefaultGroups: true
            },
            physics: {
                stabilization: true,
                barnesHut: {
                    gravitationalConstant: -8000,
                    springConstant: 0.04,
                    springLength: 120
                }
            },
            interaction: {
                hover: true,
                tooltipDelay: 100
            }
        };

        let network = new vis.Network(container, graphData, options);

        // Control buttons logic
        document.getElementById('ctrl-zoom-in').onclick = () => {
            network.moveTo({ scale: network.getScale() * 1.2 });
        };
        document.getElementById('ctrl-zoom-out').onclick = () => {
            network.moveTo({ scale: network.getScale() * 0.8 });
        };
        document.getElementById('ctrl-fit').onclick = () => {
            network.fit({ animation: true });
        };
        
        let physicsEnabled = true;
        document.getElementById('ctrl-physics').onclick = () => {
            physicsEnabled = !physicsEnabled;
            network.setOptions({ physics: { enabled: physicsEnabled } });
            document.getElementById('ctrl-physics').innerText = physicsEnabled ? '⏸ Freeze' : '▶ Unfreeze';
        };

        // Sidebar module click selection mapping
        function selectNodeById(id) {
            network.selectNodes([id]);
            displayNodeDetails(id);
            // Move network focus
            network.focus(id, { scale: 1.0, animation: true });
        }

        // Show details in Right Panel
        function displayNodeDetails(nodeId) {
            const node = data.nodes.find(n => n.id === nodeId);
            if (!node) return;

            // Name & meta
            document.getElementById('detail-name').innerText = node.label ? node.label : '/';
            document.getElementById('detail-meta').innerText = `Status: ${node.status.toUpperCase()} | Sub-files: ${node.files_count}`;

            // Files Section
            const filesSection = document.getElementById('detail-files-section');
            const filesContainer = document.getElementById('detail-files');
            if (node.files_count > 0) {
                filesSection.style.display = 'block';
                filesContainer.innerHTML = '';
                node.files.forEach(f => {
                    const fileTile = document.createElement('div');
                    fileTile.className = 'list-item';
                    fileTile.innerHTML = `<span>📄 ${f}</span>`;
                    filesContainer.appendChild(fileTile);
                });
            } else {
                filesSection.style.display = 'none';
            }

            // Context Review section
            const contentBox = document.getElementById('detail-content');
            if (node.has_context) {
                contentBox.innerHTML = marked.parse(node.content);
            } else {
                contentBox.innerHTML = `<p style="color: var(--text-muted); font-style: italic;">No CONTEXT.md rule matches this directory yet. Run <code style="color: #6366f1;">contextmesh scaffold</code> to generate rules!</p>`;
            }

            // Issues Section
            const issuesSection = document.getElementById('detail-issues-section');
            const issuesContainer = document.getElementById('detail-issues');
            if (node.issues.length > 0) {
                issuesSection.style.display = 'block';
                issuesContainer.innerHTML = '';
                node.issues.forEach(issue => {
                    const issueCard = document.createElement('div');
                    issueCard.className = `issue-card severity-${issue.severity}`;
                    
                    let snippet = '';
                    if (issue.context) {
                        snippet = `<div class="issue-snippet">> ${escapeHtml(issue.context)}</div>`;
                    }

                    issueCard.innerHTML = `
                        <div style="font-weight: 600; text-transform: uppercase; font-size: 0.75rem; margin-bottom: 0.25rem;">
                            ${issue.severity === 'error' ? '🛑 error' : '⚠️ warning'} — Line ${issue.line || 'unknown'}
                        </div>
                        <div style="font-family: var(--font-mono); margin-bottom: 0.25rem;">${issue.type}</div>
                        <div>${issue.message}</div>
                        ${snippet}
                    `;
                    issuesContainer.appendChild(issueCard);
                });
            } else {
                issuesSection.style.display = 'none';
            }
        }

        // On graph node click event
        network.on("click", function (params) {
            if (params.nodes.length > 0) {
                displayNodeDetails(params.nodes[0]);
            }
        });

        // Theme Switcher
        document.getElementById('theme-btn').onclick = () => {
            document.body.classList.toggle('light-theme');
            // Refresh colors on network dataset
            location.reload;
        };

        // Modal badge logic
        const modal = document.getElementById('badge-modal');
        const badgeBtn = document.getElementById('badge-btn');
        const closeModalBtn = document.getElementById('close-modal-btn');
        const downloadBadgeBtn = document.getElementById('download-badge-btn');

        badgeBtn.onclick = () => {
            modal.style.display = 'flex';
            // Render the Badge SVG dynamically
            const badgeSvg = generateSvgBadge(stats.health_score);
            document.getElementById('badge-preview-container').innerHTML = badgeSvg;
        };

        closeModalBtn.onclick = () => {
            modal.style.display = 'none';
        };

        window.onclick = (e) => {
            if (e.target === modal) modal.style.display = 'none';
        };

        // Generate badge SVG dynamically inside HTML
        function generateSvgBadge(health) {
            let color = '#10b981';
            if (health < 50) color = '#ef4444';
            else if (health < 75) color = '#f97316';
            else if (health < 90) color = '#f59e0b';

            return `
            <svg xmlns="http://www.w3.org/2000/svg" width="180" height="20" id="badge-svg">
              <linearGradient id="b" x2="0" y2="100%">
                <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
                <stop offset="1" stop-opacity=".1"/>
              </linearGradient>
              <mask id="a">
                <rect width="180" height="20" rx="3" fill="#fff"/>
              </mask>
              <g mask="url(#a)">
                <rect width="90" height="20" fill="#555"/>
                <rect x="90" width="90" height="20" fill="${color}"/>
                <rect width="180" height="20" fill="url(#b)"/>
              </g>
              <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
                <text x="45" y="15" fill="#010101" fill-opacity=".3">contextsync</text>
                <text x="45" y="14">contextsync</text>
                <text x="135" y="15" fill="#010101" fill-opacity=".3">${health}% health</text>
                <text x="135" y="14">${health}% health</text>
              </g>
            </svg>`;
        }

        downloadBadgeBtn.onclick = () => {
            const svgContent = document.getElementById('badge-preview-container').innerHTML.trim();
            const blob = new Blob([svgContent], { type: 'image/svg+xml;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            
            const a = document.createElement('a');
            a.href = url;
            a.download = 'contextsync-health-badge.svg';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        };

        // Utility helper functions
        function escapeHtml(text) {
            return text
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/"/g, "&quot;")
                .replace(/'/g, "&#039;");
        }
    </script>
</body>
</html>
"""
