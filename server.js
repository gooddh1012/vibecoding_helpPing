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

/////////////////////////////////
// 정적 파일
/////////////////////////////////

app.get("/", (req, res) => {
  res.sendFile(__dirname + "/public/login.html");
});

app.use(express.static("public"));

/////////////////////////////////
// MongoDB 연결
/////////////////////////////////

mongoose.connect(
  process.env.MONGO_URI +
  process.env.MONGO_DB
)
.then(() =>
  console.log("MongoDB 연결 성공")
)
.catch(err =>
  console.error("MongoDB 연결 실패:", err)
);

/////////////////////////////////
// User 스키마
/////////////////////////////////

const userSchema = new mongoose.Schema({

  email: {
    type: String,
    required: true,
    unique: true
  },

  password: {
    type: String,
    required: true
  },

  name: String,

  studentId: String

});

const User = mongoose.model(
  "User",
  userSchema
);

/////////////////////////////////
// Multer 설정
/////////////////////////////////

const storage = multer.diskStorage({

  destination: (req, file, cb) =>
    cb(null, "uploads/"),

  filename: (req, file, cb) =>
    cb(
      null,
      Date.now() + "-" + file.originalname
    )

});

const upload = multer({ storage });

/////////////////////////////////
// 상태 확인
/////////////////////////////////

app.get("/status", (req, res) => {

  res.json({

    message: "API 정상 작동 중",

    time: new Date().toISOString(),

    mongodb:
      mongoose.connection.readyState === 1
        ? "connected"
        : "disconnected"

  });

});

/////////////////////////////////
// Python 실행 함수
/////////////////////////////////

function runPython(args, res) {

  const python = spawn("python", args);

  let result = "";

  python.stdout.on("data", data => {

    result += data.toString("utf8");

  });

  python.stderr.on("data", data => {

    console.error(
      "Python stderr:",
      data.toString()
    );

  });

  python.on("close", () => {

    try {

      const jsonStart =
        result.indexOf("{");

      if (jsonStart === -1) {

        throw new Error(
          "JSON 없음"
        );

      }

      const jsonString =
        result.slice(jsonStart);

      const parsed =
        JSON.parse(jsonString);

      res.setHeader(
        "Content-Type",
        "application/json; charset=utf-8"
      );

      res.json(parsed);

    } catch (err) {

      console.error(
        "JSON 파싱 실패:"
      );

      console.error(result);

      res.status(500).json({

        error:
          "Python output parse 실패",

        raw: result

      });

    }

  });

}

/////////////////////////////////
// 회원가입
/////////////////////////////////

app.post("/signup", async (req, res) => {

  try {

    const {
      email,
      password,
      name,
      studentId
    } = req.body;

    const exists =
      await User.findOne({
        email
      });

    if (exists) {

      return res.json({

        success: false,

        message:
          "이미 존재하는 이메일입니다."

      });

    }

    if (password.length < 8) {

      return res.json({

        success: false,

        message:
          "비밀번호는 8자 이상 입력하세요."

      });

    }

    const newUser =
      new User({

        email,

        password,

        name,

        studentId

      });

    await newUser.save();

    console.log(
      "회원가입 완료:",
      email
    );

    res.json({
      success: true
    });

  } catch (err) {

    console.error(err);

    res.status(500).json({

      success: false,

      message:
        "회원가입 중 오류 발생"

    });

  }

});

/////////////////////////////////
// 로그인 (email 반환)
/////////////////////////////////

app.post("/login", async (req, res) => {

  try {

    const {
      email,
      password
    } = req.body;

    const user =
      await User.findOne({
        email
      });

    if (!user) {

      return res.json({

        success: false,

        message:
          "아이디가 존재하지 않습니다"

      });

    }

    if (
      user.password !== password
    ) {

      return res.json({

        success: false,

        message:
          "비밀번호가 일치하지 않습니다"

      });

    }

    res.json({

      success: true,

      email: email

    });

  } catch (err) {

    console.error(err);

    res.status(500).json({

      success: false,

      message:
        "로그인 중 오류 발생"

    });

  }

});

/////////////////////////////////
// 파일 업로드 (email 전달)
/////////////////////////////////

app.post(
  "/upload",

  upload.single("pdf"),

  (req, res) => {

    const email =
      req.body.email;

    console.log(
      "업로드 파일:",
      req.file.path
    );

    console.log(
      "받은 email:",
      email
    );

    // email 체크 (중요)
    if (!email) {

      return res.status(400).json({

        error:
          "email 값이 없습니다"

      });

    }

    runPython(

      [
        "main.py",
        "upload",
        req.file.path,
        email
      ],

      res

    );

  }

);

/////////////////////////////////
// 질문 (email 전달)
/////////////////////////////////

app.post(
  "/question",

  (req, res) => {

    const email =
      req.body.email;

    const question =
      req.body.question;

    console.log(
      "question email:",
      email
    );

    if (!email) {

      return res.status(400).json({

        error:
          "email 값이 없습니다"

      });

    }

    runPython(

      [
        "main.py",
        "question",
        question,
        email
      ],

      res

    );

  }

);

/////////////////////////////////
// 서버 실행
/////////////////////////////////

app.listen(PORT, () => {

  console.log(
    `Server started on http://localhost:${PORT}`
  );

});