(function () {
  document.querySelectorAll(".shot img").forEach(function (img) {
    var shot = img.closest(".shot");
    function ok() { shot.classList.remove("empty"); }
    function bad() { shot.classList.add("empty"); }
    img.addEventListener("load", ok);
    img.addEventListener("error", bad);
    if (img.complete) {
      img.naturalWidth ? ok() : bad();
    }
  });

  var form = document.getElementById("contact-form");
  if (!form) return;

  var status = form.querySelector(".form-status");
  var unwired = /FORM_ID/.test(form.action);

  form.addEventListener("submit", function (e) {
    if (unwired) {
      e.preventDefault();
      show("Form isn’t connected yet. Add a Formspree id in index.html.", "err");
      return;
    }

    e.preventDefault();
    var btn = form.querySelector("[type=submit]");
    btn.disabled = true;

    fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { Accept: "application/json" }
    }).then(function (res) {
      if (res.ok) {
        form.classList.add("sent");
        form.reset();
        show("Got it. I’ll write back.", "ok");
      } else {
        show("Didn’t send. Try again, or email instead.", "err");
        btn.disabled = false;
      }
    }).catch(function () {
      show("Didn’t send. Check the connection and try again.", "err");
      btn.disabled = false;
    });
  });

  function show(text, kind) {
    status.hidden = false;
    status.className = "form-status " + kind;
    status.textContent = text;
  }
})();
