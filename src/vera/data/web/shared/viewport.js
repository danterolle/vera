const BASE = { x: 0, y: 0, width: 1200, height: 880 };

export class GraphViewport {
  constructor(svg, onZoom, base = BASE) {
    this.svg = svg;
    this.onZoom = onZoom;
    this.base = base;
    this.view = { ...base };
    this.drag = null;
    this.bind();
    this.apply();
  }

  bind() {
    this.svg.addEventListener("wheel", event => {
      event.preventDefault();
      this.zoom(event.deltaY < 0 ? 1.14 : 0.88, event.clientX, event.clientY);
    }, { passive: false });
    this.svg.addEventListener("pointerdown", event => {
      if (event.target.closest(".node, .edge-group")) return;
      this.drag = { x: event.clientX, y: event.clientY, view: { ...this.view } };
      this.svg.setPointerCapture(event.pointerId);
      this.svg.parentElement.classList.add("dragging");
    });
    this.svg.addEventListener("pointermove", event => this.move(event));
    this.svg.addEventListener("pointerup", event => this.endDrag(event));
    this.svg.addEventListener("pointercancel", event => this.endDrag(event));
    this.svg.addEventListener("keydown", event => this.keydown(event));
  }

  move(event) {
    if (!this.drag) return;
    const bounds = this.svg.getBoundingClientRect();
    const factorX = this.drag.view.width / bounds.width;
    const factorY = this.drag.view.height / bounds.height;
    this.view.x = this.drag.view.x - (event.clientX - this.drag.x) * factorX;
    this.view.y = this.drag.view.y - (event.clientY - this.drag.y) * factorY;
    this.apply();
  }

  endDrag(event) {
    if (!this.drag) return;
    this.svg.releasePointerCapture(event.pointerId);
    this.drag = null;
    this.svg.parentElement.classList.remove("dragging");
  }

  keydown(event) {
    if (event.key === "+" || event.key === "=") this.zoom(1.2);
    else if (event.key === "-") this.zoom(0.84);
    else if (event.key === "0") this.fit();
    else if (event.key.startsWith("Arrow")) {
      const amount = 35;
      if (event.key === "ArrowLeft") this.view.x -= amount;
      if (event.key === "ArrowRight") this.view.x += amount;
      if (event.key === "ArrowUp") this.view.y -= amount;
      if (event.key === "ArrowDown") this.view.y += amount;
      this.apply();
    } else return;
    event.preventDefault();
  }

  zoom(factor, clientX, clientY) {
    const scale = this.base.width / this.view.width;
    const nextScale = Math.min(3, Math.max(0.65, scale * factor));
    const nextWidth = this.base.width / nextScale;
    const nextHeight = this.base.height / nextScale;
    const bounds = this.svg.getBoundingClientRect();
    const ratioX = clientX === undefined ? 0.5 : (clientX - bounds.left) / bounds.width;
    const ratioY = clientY === undefined ? 0.5 : (clientY - bounds.top) / bounds.height;
    const anchorX = this.view.x + this.view.width * ratioX;
    const anchorY = this.view.y + this.view.height * ratioY;
    this.view.x = anchorX - nextWidth * ratioX;
    this.view.y = anchorY - nextHeight * ratioY;
    this.view.width = nextWidth;
    this.view.height = nextHeight;
    this.apply();
  }

  fit() {
    this.view = { ...this.base };
    this.apply();
  }

  apply() {
    const { x, y, width, height } = this.view;
    this.svg.setAttribute("viewBox", `${x} ${y} ${width} ${height}`);
    this.onZoom?.(Math.round(this.base.width / width * 100));
  }
}
