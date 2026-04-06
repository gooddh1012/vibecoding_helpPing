const express = require("express");
const multer = require("multer");
const { spawn } = require("child_process");

const app = express();

app.use(express.json());
app.use(express.static("public"));

/////////////////////////////////////

const storage = multer.diskStorage({

  destination: (req, file, cb) => {

    cb(null, "uploads/");

  },

  filename: (req, file, cb) => {

    cb(
      null,
      Date.now() +
      "-" +
      file.originalname
    );

  }

});

const upload = multer({ storage });

/////////////////////////////////////
// PDF 업로드
/////////////////////////////////////

app.post(
"/upload",
upload.single("pdf"),
(req, res) => {

  const python =
  spawn(
    "python",
    [
      "main.py",
      "upload",
      req.file.path
    ]
  );

  let result = "";

  python.stdout.on(
  "data",
  data => {

    result += data.toString();

  });

  python.on(
  "close",
  () => {

    res.send(result);

  });

});

/////////////////////////////////////
// 질문
/////////////////////////////////////

app.post(
"/question",
(req, res) => {

  const python =
  spawn(
    "python",
    [
      "main.py",
      "question",
      req.body.question
    ]
  );

  let result = "";

  python.stdout.on(
  "data",
  data => {

    result += data.toString();

  });

  python.on(
  "close",
  () => {

    res.send(result);

  });

});

/////////////////////////////////////
// 요약
/////////////////////////////////////

app.get(
"/summary",
(req, res) => {

  const python =
  spawn(
    "python",
    [
      "main.py",
      "summary"
    ]
  );

  let result = "";

  python.stdout.on(
  "data",
  data => {

    result += data.toString();

  });

  python.on(
  "close",
  () => {

    res.send(result);

  });

});

/////////////////////////////////////

app.listen(3000, () => {

  console.log(
    "Server started"
  );

});