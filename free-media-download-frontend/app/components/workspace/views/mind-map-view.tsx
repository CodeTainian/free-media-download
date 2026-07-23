"use client";

import { useMemo, useState, type CSSProperties } from "react";
import { downloadTextFile, timestampUrl } from "../../../lib/api/format";
import type { MindMap, MindMapNode } from "../../../lib/api/types";
import type { BubbleDictionary } from "../../../lib/i18n/messages/en-US";

function escapeXml(value: string) {
  return value.replace(
    /[<>&'"]/g,
    (character) =>
      ({
        "<": "&lt;",
        ">": "&gt;",
        "&": "&amp;",
        "'": "&apos;",
        '"': "&quot;",
      })[character] ?? character,
  );
}

export function MindMapView({
  map,
  sourceUrl,
  dictionary,
}: {
  map: MindMap;
  sourceUrl: string;
  dictionary: BubbleDictionary;
}) {
  const [zoom, setZoom] = useState(1);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const nodes = useMemo(
    () => new Map(map.nodes.map((node) => [node.id, node])),
    [map.nodes],
  );

  function toggle(node: MindMapNode) {
    if (!node.children.length) return;
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(node.id)) next.delete(node.id);
      else next.add(node.id);
      return next;
    });
  }

  function renderNode(nodeId: string, depth = 0) {
    const node = nodes.get(nodeId);
    if (!node) return null;
    const expanded = !collapsed.has(node.id);
    return (
      <li
        key={node.id}
        role="treeitem"
        aria-selected="false"
        aria-expanded={node.children.length ? expanded : undefined}
      >
        <div className="mind-map-node" data-kind={node.type}>
          <button type="button" onClick={() => toggle(node)}>
            <strong>{node.label}</strong>
            <span>{node.description}</span>
          </button>
          <a
            href={timestampUrl(sourceUrl, node.timestamp_seconds)}
            target="_blank"
            rel="noreferrer"
            aria-label={`${dictionary.workspace.openAt} ${node.label}`}
          >
            ↗
          </a>
        </div>
        {expanded && node.children.length ? (
          <ul role="group">
            {node.children.map((child) => renderNode(child, depth + 1))}
          </ul>
        ) : null}
      </li>
    );
  }

  function exportImage() {
    const visible = map.nodes.filter((node) => !collapsed.has(node.id));
    const width = 1200;
    const rowHeight = 68;
    const height = Math.max(300, visible.length * rowHeight + 80);
    const body = visible
      .map(
        (node, index) =>
          `<g transform="translate(40 ${50 + index * rowHeight})"><rect width="1120" height="52" rx="14" fill="${node.type === "root" ? "#fbe9df" : "#fff"}" stroke="#dce3df"/><text x="18" y="23" font-family="system-ui" font-weight="700" font-size="15" fill="#1d2925">${escapeXml(node.label)}</text><text x="18" y="42" font-family="system-ui" font-size="11" fill="#62706a">${escapeXml(node.description.slice(0, 150))}</text></g>`,
      )
      .join("");
    downloadTextFile(
      "bubble-mind-map.svg",
      `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#f7f7f4"/>${body}</svg>`,
      "image/svg+xml",
    );
  }

  return (
    <div className="mind-map-view">
      <header className="artifact-view-header">
        <p className="section-kicker">{dictionary.workspace.tabs.mind_map}</p>
        <h2>{dictionary.workspace.mindMapHeading}</h2>
        <div className="map-controls" aria-label={dictionary.workspace.mapControls}>
          <button type="button" onClick={() => setZoom((value) => Math.max(0.7, value - 0.1))}>−</button>
          <output>{Math.round(zoom * 100)}%</output>
          <button type="button" onClick={() => setZoom((value) => Math.min(1.5, value + 0.1))}>+</button>
          <button type="button" onClick={() => { setZoom(1); setCollapsed(new Set()); }}>
            {dictionary.workspace.recenter}
          </button>
          <button type="button" onClick={exportImage}>{dictionary.workspace.exportImage}</button>
        </div>
      </header>
      <div className="mind-map-canvas" style={{ "--map-zoom": zoom } as CSSProperties}>
        <ul role="tree" aria-label={dictionary.workspace.mindMapHeading}>
          {renderNode(map.root_id)}
        </ul>
      </div>
    </div>
  );
}
