/* List-your-business form: mailto by default, or POST to a configured endpoint. */
(function () {
  const form = document.getElementById("partner-form");
  if (!form) return;
  const cfg = window.SIPSPOT_CONFIG || window.REFILLMAP_CONFIG || {};
  const status = document.getElementById("form-status");

  function setStatus(msg, isError) {
    if (!status) return;
    status.textContent = msg;
    status.classList.toggle("error", !!isError);
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form).entries());
    const endpoint = (cfg.partnerFormEndpoint || "").trim();

    if (endpoint) {
      const body = new FormData(form);
      fetch(endpoint, {
        method: "POST",
        body: body,
        headers: { Accept: "application/json" }
      })
        .then(function (res) {
          if (!res.ok) throw new Error("The form endpoint returned " + res.status);
          setStatus("Thanks. We have received your listing request.");
          form.reset();
        })
        .catch(function (err) {
          setStatus("Could not send the form (" + err.message + "). You can email " + (cfg.contactEmail || "") + " instead.", true);
        });
      return;
    }

    const email = cfg.contactEmail || "hello@sipspot.co.uk";
    const lines = [
      "SipSpot cooler partner listing request",
      "",
      "Business name: " + (data.business || ""),
      "Contact name: " + (data.contact_name || ""),
      "Email: " + (data.email || ""),
      "Address: " + (data.address || ""),
      "Postcode: " + (data.postcode || ""),
      "Opening hours: " + (data.hours || ""),
      "Water type: " + (data.water_type || ""),
      "Chilled: " + (data.chilled || ""),
      "Walk-in free (no purchase needed): " + (data.walk_in_free || "no"),
      "Notes: " + (data.notes || "")
    ];
    const subject = "SipSpot partner listing: " + (data.business || "new business");
    const href =
      "mailto:" + encodeURIComponent(email) +
      "?subject=" + encodeURIComponent(subject) +
      "&body=" + encodeURIComponent(lines.join("\n"));
    window.location.href = href;
    setStatus("Your email app should open with the details filled in. If it does not, write to " + email + " instead.");
  });
})();
