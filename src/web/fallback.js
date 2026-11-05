// Fallback: if the script above never ran (for example a damaged data file that is not valid JavaScript), say so on the page.
if (!window.__dipDrawn) {
  var f = document.getElementById('fail');
  f.innerHTML = '<span class="ic" aria-hidden="true">!</span><p><b>This page could not read its data file.</b> The file may be damaged or cut short. The nightly run writes a plain-text summary too: output/digest.md.</p>';
  f.hidden = false;
}
