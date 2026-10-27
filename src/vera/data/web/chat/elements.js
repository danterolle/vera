export function text(parent, tag, value, className = "") {
  const element = document.createElement(tag);
  element.textContent = String(value ?? "");
  if (className) element.className = className;
  parent.append(element);
  return element;
}

export function button(parent, label, callback, className = "action-button") {
  const element = text(parent, "button", label, className);
  element.type = "button";
  element.addEventListener("click", callback);
  return element;
}

export function prose(parent, content) {
  const area = document.createElement("div");
  area.className = "prose";
  String(content || "").split(/\n\s*\n/).filter(Boolean).forEach(paragraph => {
    text(area, "p", paragraph);
  });
  parent.append(area);
}
