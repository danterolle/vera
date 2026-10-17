export function positions(data, width, height) {
  const selected = new Set(data.selected_ids);
  const nodes = data.nodes.map((node, index) => {
    const angle = index * Math.PI * 2 / Math.max(1, data.nodes.length);
    return {...node, x: width / 2 + Math.cos(angle) * width * .32,
      y: height / 2 + Math.sin(angle) * height * .32};
  });
  const map = new Map(nodes.map(node => [node.id, node]));
  const center = nodes.find(node => selected.has(node.id));
  if (center && selected.size === 1) { center.x = width / 2; center.y = height / 2; }
  for (let step = 0; step < 260; step++) {
    const forces = new Map(nodes.map(node => [node.id, {x: 0, y: 0}]));
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      const dx = a.x - b.x || .1, dy = a.y - b.y || .1;
      const distance = Math.max(20, Math.hypot(dx, dy));
      const collision = Math.abs(dx) < 310 && Math.abs(dy) < 145;
      const force = Math.min(50, 95000 / distance ** 2 + (collision ? 22 : 0));
      const fx = dx / distance * force, fy = dy / distance * force;
      forces.get(a.id).x += fx; forces.get(a.id).y += fy;
      forces.get(b.id).x -= fx; forces.get(b.id).y -= fy;
    }
    for (const edge of data.edges) {
      const a = map.get(edge.source), b = map.get(edge.target);
      if (!a || !b) continue;
      const dx = b.x - a.x, dy = b.y - a.y, distance = Math.max(1, Math.hypot(dx, dy));
      const spring = (distance - 370) * .015;
      const fx = dx / distance * spring, fy = dy / distance * spring;
      forces.get(a.id).x += fx; forces.get(a.id).y += fy;
      forces.get(b.id).x -= fx; forces.get(b.id).y -= fy;
    }
    for (const node of nodes) {
      if (node === center && selected.size === 1) continue;
      const f = forces.get(node.id);
      node.x = Math.min(width - 160, Math.max(160,
        node.x + Math.max(-12, Math.min(12, f.x + (width / 2 - node.x) * .003))));
      node.y = Math.min(height - 70, Math.max(70,
        node.y + Math.max(-12, Math.min(12, f.y + (height / 2 - node.y) * .003))));
    }
  }
  return map;
}
