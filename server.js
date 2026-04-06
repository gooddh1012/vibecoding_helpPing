const express = require("express");
const multer = require("multer");
const { spawn } = require("child_process");
const mongoose = require("mongoose");
const morgan = require("morgan");
require("dotenv").config();

const app = express();
const PORT = process.env.PORT || 3000;

app.use(morgan("dev"));
app.use(express.json());
app.use(express.static("public"));

/////////////////////////////////
// MongoDB 연결
/////////////////////////////////
mongoose.connect(process.env.MONGO_URI)
  .then(() => console.log("MongoDB 연결 성공"))
  .catch(err => console.error("❌ MongoDB 연결 실패:", err));

/////////////////////////////////
// Multer 설정
/////////////////////////////////
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, "uploads/"),
  filename: (req, file, cb) =>
    cb(null, Date.now() + "-" + file.originalname)
});
const upload = multer({ storage });

/////////////////////////////////
// 상태 확인
/////////////////////////////////
app.get("/status", (req, res) => {
  res.json({
    message: "API 정상 작동 중",
    time: new Date().toISOString(),
    mongodb: mongoose.connection.readyState === 1 ? "connected" : "disconnected"
  });
});

/////////////////////////////////
// Python 실행 공통 함수
/////////////////////////////////
/////////////////////////////////
// Python 실행 공통 함수
/////////////////////////////////
function runPython(args, res) {
  const python = spawn("python", args);
  let result = "";

  python.stdout.on("data", data => {
    result += data.toString();
  });

  python.stderr.on("data", data => {
    console.error("Python Error:", data.toString());
  });

  python.on("close", () => {
    try {
      // Python에서 ensure_ascii=False로 출력하면 한글 그대로 JSON 파싱 가능
      const parsed = JSON.parse(result);

      // ★ 여기서 UTF-8 명시
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.json(parsed);
    } catch {
      // JSON 파싱 실패 시 원본 출력
      res.send(result);
    }
  });
}

/////////////////////////////////
// 업로드
/////////////////////////////////
app.post("/upload", upload.single("pdf"), (req, res) => {
  console.log("업로드 파일:", req.file.path);
  runPython(["main.py", "upload", req.file.path], res);
});

/////////////////////////////////
// 질문
/////////////////////////////////
app.post("/question", (req, res) => {
  runPython(["main.py", "question", req.body.question], res);
});

/////////////////////////////////
// 전체 요약
/////////////////////////////////
app.get("/summary", (req, res) => {
  runPython(["main.py", "summary"], res);
});

/////////////////////////////////
// 서버 실행
/////////////////////////////////
app.listen(PORT, () => {
  console.log(`Server started on http://localhost:${PORT}`);
});