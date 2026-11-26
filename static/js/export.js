(function () {
  var form = document.querySelector("[data-export-form]");
  if (!form) return;
  var statusBox = document.querySelector("[data-export-status]");
  var button = form.querySelector("[data-export-button]");
  var POLL_MS = 1500;
  var MAX_POLLS = 80;

  function csrfToken() {
    var input = form.querySelector("input[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function show(message, isError) {
    statusBox.textContent = message;
    statusBox.classList.toggle("is-error", Boolean(isError));
  }

  function showLink(url, rows) {
    statusBox.textContent = "Đã xuất xong " + rows + " dòng. ";
    statusBox.classList.remove("is-error");
    var link = document.createElement("a");
    link.href = url;
    link.className = "mv-btn mv-btn-crimson";
    link.textContent = "Tải tệp Excel";
    statusBox.appendChild(link);
  }

  function errorText(body, fallback) {
    if (!body) return fallback;
    if (body.detail) return body.detail;
    var parts = [];
    Object.keys(body).forEach(function (key) {
      var value = body[key];
      parts.push(Array.isArray(value) ? value.join(" ") : String(value));
    });
    return parts.join(" ") || fallback;
  }

  function request(url, options) {
    return fetch(url, Object.assign({
      credentials: "same-origin",
      headers: { "Accept": "application/json", "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
    }, options)).then(function (resp) {
      return resp.json().catch(function () { return null; }).then(function (body) {
        if (!resp.ok) throw new Error(errorText(body, "Lỗi máy chủ (" + resp.status + ")."));
        return body;
      });
    });
  }

  function poll(statusUrl, count) {
    if (count >= MAX_POLLS) {
      show("Quá thời gian chờ. Hãy kiểm tra Celery worker rồi thử lại.", true);
      button.disabled = false;
      return;
    }
    request(statusUrl, { method: "GET" }).then(function (body) {
      if (body.status === "success") {
        showLink(body.download_url, body.rows);
        button.disabled = false;
      } else if (body.status === "failure") {
        show("Xuất báo cáo thất bại, vui lòng thử lại.", true);
        button.disabled = false;
      } else {
        show(body.status === "running" ? "Đang tạo tệp Excel..." : "Đang chờ xử lý...");
        window.setTimeout(function () { poll(statusUrl, count + 1); }, POLL_MS);
      }
    }).catch(function (err) {
      show(err.message, true);
      button.disabled = false;
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var payload = {
      date_from: form.elements.date_from.value,
      date_to: form.elements.date_to.value,
    };
    if (!payload.date_from || !payload.date_to) {
      show("Vui lòng chọn đủ ngày bắt đầu và ngày kết thúc.", true);
      return;
    }
    button.disabled = true;
    show("Đang gửi yêu cầu...");
    var startUrl = form.dataset.startUrl;
    request(startUrl, { method: "POST", body: JSON.stringify(payload) }).then(function (body) {
      poll(startUrl + body.task_id + "/", 0);
    }).catch(function (err) {
      show(err.message, true);
      button.disabled = false;
    });
  });
})();
