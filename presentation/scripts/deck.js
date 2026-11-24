const slides = [...document.querySelectorAll(".slides > section")];

slides.forEach((slide, index) => {
  const footer = document.createElement("footer");
  footer.className = "deck-footer";
  footer.textContent = `VERA  /  ${String(index + 1).padStart(2, "0")} : ${slides.length}`;
  slide.append(footer);
});

Reveal.initialize({
  hash: true, width: 1210, height: 681, margin: 0, center: false,
  transition: "fade", pdfSeparateFragments: false, pdfMaxPagesPerSlide: 1,
});
