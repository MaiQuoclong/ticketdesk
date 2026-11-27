(function () {
  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function setup(zone) {
    var input = zone.querySelector('input[type="file"]');
    var list = zone.querySelector("[data-file-list]");
    var errorBox = zone.querySelector("[data-file-error]");
    var maxSize = parseInt(zone.dataset.maxSize, 10);
    var maxFiles = parseInt(zone.dataset.maxFiles, 10);
    var allowed = zone.dataset.accept.split(",");
    var files = [];

    function sync() {
      var dt = new DataTransfer();
      files.forEach(function (f) { dt.items.add(f); });
      input.files = dt.files;
      list.innerHTML = "";
      files.forEach(function (f, index) {
        var li = document.createElement("li");
        var name = document.createElement("span");
        name.textContent = f.name + " (" + formatSize(f.size) + ")";
        var remove = document.createElement("button");
        remove.type = "button";
        remove.className = "btn-close";
        remove.setAttribute("aria-label", "Bỏ tệp " + f.name);
        remove.addEventListener("click", function () {
          files.splice(index, 1);
          sync();
        });
        li.appendChild(name);
        li.appendChild(remove);
        list.appendChild(li);
      });
    }

    function add(newFiles) {
      var errors = [];
      Array.prototype.forEach.call(newFiles, function (f) {
        var ext = f.name.split(".").pop().toLowerCase();
        if (allowed.indexOf(ext) === -1) {
          errors.push("“" + f.name + "” sai định dạng.");
        } else if (f.size > maxSize) {
          errors.push("“" + f.name + "” vượt quá 5 MB.");
        } else if (files.length >= maxFiles) {
          errors.push("Chỉ đính kèm tối đa " + maxFiles + " tệp.");
        } else if (!files.some(function (x) { return x.name === f.name && x.size === f.size; })) {
          files.push(f);
        }
      });
      errorBox.textContent = errors.join(" ");
      sync();
    }

    input.addEventListener("change", function () {
      var picked = Array.prototype.slice.call(input.files);
      add(picked);
    });

    ["dragenter", "dragover"].forEach(function (evt) {
      zone.addEventListener(evt, function (e) {
        e.preventDefault();
        zone.classList.add("is-dragover");
      });
    });
    ["dragleave", "drop"].forEach(function (evt) {
      zone.addEventListener(evt, function (e) {
        e.preventDefault();
        zone.classList.remove("is-dragover");
      });
    });
    zone.addEventListener("drop", function (e) {
      if (e.dataTransfer && e.dataTransfer.files) add(e.dataTransfer.files);
    });
  }

  document.querySelectorAll("[data-dropzone]").forEach(setup);
})();
