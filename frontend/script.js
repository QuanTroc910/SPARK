// Địa chỉ backend Flask. Đổi lại nếu bạn chạy backend ở port/host khác.
const API_BASE = "http://localhost:5000";

// Biến "nhớ" trạng thái hiện tại của trang (giống như state trong React,
// nhưng ở đây làm bằng tay vì chưa dùng framework).
let currentFileId = null;

const fileInput = document.getElementById("file-input");
const dropZone = document.getElementById("drop-zone");
const dropZoneText = document.getElementById("drop-zone-text");
const uploadBtn = document.getElementById("upload-btn");
const detectBtn = document.getElementById("detect-btn");

// ====== KÉO-THẢ FILE (chỉ để tiện, không bắt buộc phải dùng) ======
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  if (e.dataTransfer.files.length > 0) {
    fileInput.files = e.dataTransfer.files;
    dropZoneText.textContent = `📄 Đã chọn: ${fileInput.files[0].name}`;
  }
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) {
    dropZoneText.textContent = `📄 Đã chọn: ${fileInput.files[0].name}`;
  }
});

function setStepActive(stepNumber) {
  [1, 2, 3].forEach((n) => {
    document.getElementById(`step-indicator-${n}`).classList.toggle("active", n <= stepNumber);
  });
}

function setButtonLoading(button, isLoading, loadingText, normalText) {
  button.disabled = isLoading;
  button.textContent = isLoading ? loadingText : normalText;
}

// ====== BƯỚC 1: UPLOAD FILE ======
uploadBtn.addEventListener("click", async () => {
  const file = fileInput.files[0];
  if (!file) {
    alert("Hãy chọn 1 file trước đã");
    return;
  }

  setButtonLoading(uploadBtn, true, "Đang upload...", "Upload");

  // FormData: cách trình duyệt gửi FILE lên server (không dùng JSON thường
  // được vì JSON không chứa được dữ liệu nhị phân của file).
  const formData = new FormData();
  formData.append("file", file);

  let response;
  try {
    response = await fetch(`${API_BASE}/api/upload`, { method: "POST", body: formData });
  } catch (err) {
    alert("Không gọi được backend. Kiểm tra xem python3 app.py có đang chạy không.");
    setButtonLoading(uploadBtn, false, "Đang upload...", "Upload");
    return;
  }

  setButtonLoading(uploadBtn, false, "Đang upload...", "Upload");

  if (!response.ok) {
    alert("Upload thất bại, kiểm tra lại file hoặc log của backend.");
    return;
  }

  const data = await response.json(); // { file_id, columns, row_count }
  currentFileId = data.file_id;

  document.getElementById("upload-status").textContent =
    `✅ Đã upload: ${data.row_count} dòng, ${data.columns.length} cột.`;

  renderColumnConfigForm(data.columns);
  document.getElementById("config-section").hidden = false;
  setStepActive(2);
});

// ====== BƯỚC 2: DỰNG FORM CHỌN NOISE CHO TỪNG CỘT ======
// Demo này chỉ làm 3 loại noise cơ bản (missing_value, format_noise,
// out_of_range) cho dễ nhìn. Muốn thêm outlier/inconsistent_category/... thì
// làm tương tự: thêm checkbox + input tham số, rồi đọc lại trong
// buildColumnConfigs() bên dưới.
function renderColumnConfigForm(columns) {
  const container = document.getElementById("column-config-list");
  container.innerHTML = "";

  columns.forEach((col) => {
    const div = document.createElement("div");
    div.className = "column-config";
    div.dataset.col = col; // gắn tên cột vào chính div để lát nữa dễ đọc lại
    div.innerHTML = `
      <span class="col-name">${col}</span>
      <label>Kiểu:
        <select class="dtype">
          <option value="text">text</option>
          <option value="integer">integer</option>
          <option value="float">float</option>
          <option value="email">email</option>
          <option value="phone">phone</option>
          <option value="date">date</option>
          <option value="category">category</option>
        </select>
      </label>
      <label><input type="checkbox" class="nt-missing" /> Missing value</label>
      <label><input type="checkbox" class="nt-format" /> Format noise</label>
      <label>
        <input type="checkbox" class="nt-range" /> Out of range
        min <input type="number" class="min-value" />
        max <input type="number" class="max-value" />
      </label>
    `;
    container.appendChild(div);
  });
}

// Đọc lại toàn bộ form -> dựng thành mảng JSON config, ĐÚNG format mà
// backend (_config_from_json trong app.py) đang mong đợi.
function buildColumnConfigs() {
  const configs = [];

  document.querySelectorAll(".column-config").forEach((div) => {
    const column = div.dataset.col;
    const dtype = div.querySelector(".dtype").value;
    const noiseTypes = [];

    if (div.querySelector(".nt-missing").checked) {
      noiseTypes.push("missing_value");
    }
    if (div.querySelector(".nt-format").checked) {
      noiseTypes.push("format_noise");
    }

    let minValue = null;
    let maxValue = null;
    if (div.querySelector(".nt-range").checked) {
      noiseTypes.push("out_of_range");
      const minRaw = div.querySelector(".min-value").value;
      const maxRaw = div.querySelector(".max-value").value;
      minValue = minRaw === "" ? null : parseFloat(minRaw);
      maxValue = maxRaw === "" ? null : parseFloat(maxRaw);
    }

    // Cột nào user không tick gì cả thì bỏ qua, không gửi lên backend.
    if (noiseTypes.length === 0) return;

    configs.push({
      column,
      dtype,
      noise_types: noiseTypes,
      min_value: minValue,
      max_value: maxValue,
    });
  });

  return configs;
}

// ====== BƯỚC 3: GỌI BACKEND DETECT + HIỂN THỊ KẾT QUẢ ======
detectBtn.addEventListener("click", async () => {
  const columnConfigs = buildColumnConfigs();
  if (columnConfigs.length === 0) {
    alert("Hãy chọn ít nhất 1 loại noise cho ít nhất 1 cột");
    return;
  }

  setButtonLoading(detectBtn, true, "Đang detect...", "🔍 Detect Noise");

  let response;
  try {
    response = await fetch(`${API_BASE}/api/detect-noise`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_id: currentFileId, column_configs: columnConfigs }),
    });
  } catch (err) {
    alert("Không gọi được backend.");
    setButtonLoading(detectBtn, false, "Đang detect...", "🔍 Detect Noise");
    return;
  }

  setButtonLoading(detectBtn, false, "Đang detect...", "🔍 Detect Noise");

  if (!response.ok) {
    alert("Detect thất bại, kiểm tra console/backend log.");
    return;
  }

  const data = await response.json();
  renderResults(data);
  setStepActive(3);
});

// Map noise_type -> tên class badge CSS tương ứng (định nghĩa màu trong style.css)
function noiseBadge(noiseType) {
  return `<span class="badge badge-${noiseType}">${noiseType}</span>`;
}

// Cột "noise_reasons" backend trả về dạng chuỗi "age:out_of_range, email:format_noise".
// Hàm này tách chuỗi đó ra và vẽ lại thành các badge màu cho dễ nhìn.
function formatNoiseReasons(value) {
  if (!value) return "";
  return value
    .split(",")
    .map((part) => {
      const [column, noiseType] = part.trim().split(":");
      if (!noiseType) return part;
      return `<strong>${column}</strong> ${noiseBadge(noiseType)}`;
    })
    .join(" ");
}

function renderResults(data) {
  document.getElementById("result-section").hidden = false;

  document.getElementById("stat-total-rows").textContent = data.total_rows;
  document.getElementById("stat-flagged-rows").textContent = data.total_flagged_rows;
  document.getElementById("stat-total-findings").textContent = data.findings.length;

  const rows = data.flagged_rows;
  const head = document.getElementById("result-table-head");
  const body = document.getElementById("result-table-body");
  const emptyMsg = document.getElementById("result-empty");
  head.innerHTML = "";
  body.innerHTML = "";

  if (rows.length === 0) {
    emptyMsg.hidden = false;
    document.getElementById("result-table").hidden = true;
    return;
  }
  emptyMsg.hidden = true;
  document.getElementById("result-table").hidden = false;

  // Dùng chính các key của object đầu tiên để làm tên cột cho bảng HTML.
  const columns = Object.keys(rows[0]);
  columns.forEach((c) => {
    const th = document.createElement("th");
    th.textContent = c;
    head.appendChild(th);
  });

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((c) => {
      const td = document.createElement("td");
      if (c === "noise_reasons") {
        td.innerHTML = formatNoiseReasons(row[c]); // render badge màu thay vì text thô
      } else {
        td.textContent = row[c];
      }
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
}
