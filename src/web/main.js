render();   // every row starts collapsed, so the table and its sparklines are visible without scrolling past an open detail
} catch (e) {
  noteFail('the page', null, e);               // something outside the per-section guards broke: say so instead of a blank page
} finally {
  window.__dipDrawn = true;
}
})();
