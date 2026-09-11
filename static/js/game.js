(function () {
  const canvas = document.getElementById("game-canvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;

  const WIDTH = canvas.width;
  const HEIGHT = canvas.height;
  const GROUND_Y = HEIGHT - 24;
  const GRAVITY = 0.55;
  const JUMP_VELOCITY = -9.5;
  const PLAYER_X = 40;
  const PLAYER_W = 28;
  const PLAYER_H = 26;
  const HIGH_SCORE_KEY = "keep-runner-high-score";

  const COLOR_BG = "#f5f1e8";
  const COLOR_STONE = "#292524";
  const COLOR_AMBER = "#b45309";
  const COLOR_TEXT = "#292524";

  let highScore = 0;
  try {
    highScore = parseInt(localStorage.getItem(HIGH_SCORE_KEY), 10) || 0;
  } catch (e) {}

  let rafId = null;
  let player, obstacles, speed, spawnTimer, spawnInterval, frame, score, gameOver, scorePrompted;

  function resetState() {
    player = { y: GROUND_Y - PLAYER_H, vy: 0, jumping: false };
    obstacles = [];
    speed = 3.2;
    spawnTimer = 0;
    spawnInterval = 70;
    frame = 0;
    score = 0;
    gameOver = false;
    scorePrompted = false;
  }

  function renderLeaderboard(entries) {
    const list = document.getElementById("leaderboard-list");
    if (!list) return;
    list.innerHTML = "";
    if (!entries || entries.length === 0) {
      const empty = document.createElement("li");
      empty.className = "px-1 py-2 text-stone-500";
      empty.textContent = "No scores yet — be the first!";
      list.appendChild(empty);
      return;
    }
    entries.forEach(function (entry, i) {
      const li = document.createElement("li");
      li.className = "flex justify-between px-1 py-2";
      const rank = document.createElement("span");
      rank.textContent = (i + 1) + ". " + entry.initials;
      const points = document.createElement("span");
      points.textContent = String(entry.score);
      li.appendChild(rank);
      li.appendChild(points);
      list.appendChild(li);
    });
  }

  function promptForLeaderboard(finalScore) {
    const raw = window.prompt("Game over! Enter 3 letters for the leaderboard:", "");
    const initials = (raw || "").trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(initials)) return;
    fetch("/game/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ initials: initials, score: finalScore }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (data.leaderboard) renderLeaderboard(data.leaderboard);
      })
      .catch(function () {});
  }

  function jump() {
    if (gameOver) {
      resetState();
      return;
    }
    if (!player.jumping) {
      player.vy = JUMP_VELOCITY;
      player.jumping = true;
    }
  }

  function spawnObstacle() {
    const h = 14 + Math.floor(Math.random() * 22);
    obstacles.push({ x: WIDTH, y: GROUND_Y - h, w: 16, h: h });
  }

  function update() {
    frame++;
    player.vy += GRAVITY;
    player.y += player.vy;
    if (player.y >= GROUND_Y - PLAYER_H) {
      player.y = GROUND_Y - PLAYER_H;
      player.vy = 0;
      player.jumping = false;
    }

    spawnTimer++;
    if (spawnTimer >= spawnInterval) {
      spawnTimer = 0;
      spawnInterval = 55 + Math.floor(Math.random() * 55);
      spawnObstacle();
    }

    for (let i = obstacles.length - 1; i >= 0; i--) {
      obstacles[i].x -= speed;
      if (obstacles[i].x + obstacles[i].w < 0) obstacles.splice(i, 1);
    }

    speed += 0.0025;
    score = Math.floor(frame / 6);

    const px = PLAYER_X, py = player.y, pw = PLAYER_W, ph = PLAYER_H;
    for (const o of obstacles) {
      if (px < o.x + o.w && px + pw > o.x && py < o.y + o.h && py + ph > o.y) {
        gameOver = true;
        if (score > highScore) {
          highScore = score;
          try {
            localStorage.setItem(HIGH_SCORE_KEY, String(highScore));
          } catch (e) {}
        }
        break;
      }
    }
  }

  function drawCastlePlayer(x, y) {
    ctx.fillStyle = COLOR_STONE;
    ctx.fillRect(x, y + 8, PLAYER_W, PLAYER_H - 8);
    ctx.fillRect(x, y, 6, 8);
    ctx.fillRect(x + 11, y, 6, 8);
    ctx.fillRect(x + 22, y, 6, 8);
    ctx.fillStyle = COLOR_AMBER;
    ctx.fillRect(x + 11, y + 16, 6, PLAYER_H - 16);
  }

  function drawObstacle(o) {
    ctx.fillStyle = COLOR_STONE;
    ctx.fillRect(o.x, o.y, o.w, o.h);
  }

  function draw() {
    ctx.clearRect(0, 0, WIDTH, HEIGHT);
    ctx.fillStyle = COLOR_BG;
    ctx.fillRect(0, 0, WIDTH, HEIGHT);

    ctx.fillStyle = COLOR_AMBER;
    ctx.fillRect(0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y);

    drawCastlePlayer(PLAYER_X, player.y);
    for (const o of obstacles) drawObstacle(o);

    ctx.fillStyle = COLOR_TEXT;
    ctx.font = "12px monospace";
    ctx.textAlign = "left";
    ctx.fillText("Score: " + score, 8, 16);
    ctx.fillText("Best: " + highScore, 8, 30);

    if (gameOver) {
      ctx.textAlign = "center";
      ctx.font = "16px monospace";
      ctx.fillText("GAME OVER", WIDTH / 2, HEIGHT / 2 - 10);
      ctx.font = "11px monospace";
      ctx.fillText("Score: " + score, WIDTH / 2, HEIGHT / 2 + 8);
      ctx.fillText("Press Space or click to retry", WIDTH / 2, HEIGHT / 2 + 24);
      ctx.textAlign = "left";
    }
  }

  function loop() {
    if (!gameOver) update();
    draw();
    if (gameOver && !scorePrompted) {
      scorePrompted = true;
      promptForLeaderboard(score);
    }
    rafId = requestAnimationFrame(loop);
  }

  function stopLoop() {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  }

  function startFreshRun() {
    resetState();
    stopLoop();
    rafId = requestAnimationFrame(loop);
  }

  document.addEventListener("keydown", function (e) {
    if (e.code === "Space" || e.code === "ArrowUp") {
      e.preventDefault();
      jump();
    }
  });

  canvas.addEventListener("click", jump);

  startFreshRun();
})();
