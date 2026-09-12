// Địa chỉ backend Flask. Đổi lại nếu bạn chạy backend ở port/host khác.
const API_BASE = "http://localhost:5000";

// Biến "nhớ" trạng thái hiện tại của trang (giống như state trong React,
// nhưng ở đây làm bằng tay vì chưa dùng framework).
let currentFileId = null;

// ====== BƯỚC 1: UPLOAD FILE ======
document.getElementById("upload-btn").addEventListener("click", async () => {
  const fileInput = document.getElementById("file-input");
  const file = fileInput.files[0];
  if (!file) {
    alert("Hãy chọn 1 file trước đã");
    return;
  }

  // FormData: cách trình duyệt gửi FILE lên server (không dùng JSON thường
  // được vì JSON không chứa được dữ liệu nhị phân của file).
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    alert("Upload thất bại, kiểm tra lại backend có đang chạy không.");
    return;
  }

  const data = await response.json(); // { file_id, columns, row_count }
  currentFileId = data.file_id;

  document.getElementById("upload-status").textContent =
    `Đã upload: ${data.row_count} dòng, ${data.columns.length} cột.`;

  renderColumnConfigForm(data.columns);
  document.getElementById("config-section").hidden = false;
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
      <strong>${col}</strong><br />
      Kiểu dữ liệu:
      <select class="dtype">
        <option value="text">text</option>
        <option value="integer">integer</option>
        <option value="float">float</option>
        <option value="email">email</option>
        <option value="phone">phone</option>
        <option value="date">date</option>
        <option value="category">category</option>
      </select>
      <label><input type="checkbox" class="nt-missing" /> Missing value</label>
      <label><input type="checkbox" class="nt-format" /> Format noise</label>
      <label>
        <input type="checkbox" class="nt-range" /> Out of range
        (min <input type="number" class="min-value" style="width:60px" />
         max <input type="number" class="max-value" style="width:60px" />)
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
document.getElementById("detect-btn").addEventListener("click", async () => {
  const columnConfigs = buildColumnConfigs();
  if (columnConfigs.length === 0) {
    alert("Hãy chọn ít nhất 1 loại noise cho ít nhất 1 cột");
    return;
  }

  const response = await fetch(`${API_BASE}/api/detect-noise`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      file_id: currentFileId,
      column_configs: columnConfigs,
    }),
  });

  if (!response.ok) {
    alert("Detect thất bại, kiểm tra console/backend log.");
    return;
  }

  const data = await response.json();
  renderResults(data);
});

function renderResults(data) {
  document.getElementById("result-section").hidden = false;
  document.getElementById("result-summary").textContent =
    `Tổng ${data.total_rows} dòng, ${data.total_flagged_rows} dòng có noise, ` +
    `${data.findings.length} ô lỗi được phát hiện.`;

  const rows = data.flagged_rows;
  const head = document.getElementById("result-table-head");
  const body = document.getElementById("result-table-body");
  head.innerHTML = "";
  body.innerHTML = "";

  if (rows.length === 0) return;

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
      td.textContent = row[c];
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
}
