(function () {
  var canvas = document.getElementById('space');
  if (!canvas || !window.THREE) return;

  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
  } catch (error) {
    canvas.hidden = true;
    console.error('The animated space background could not start.', error);
    return;
  }

  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setClearColor(0x000000, 0);

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(50, 1, 0.1, 120);
  camera.position.z = 12;
  scene.add(new THREE.AmbientLight(0x9a9aa2, 0.78));
  var sun = new THREE.DirectionalLight(0xffe6c4, 1.8);
  sun.position.set(-6, 5, 8);
  scene.add(sun);

  var seed = 99;
  function random() {
    seed |= 0;
    seed = seed + 0x6D2B79F5 | 0;
    var value = Math.imul(seed ^ seed >>> 15, 1 | seed);
    value = value + Math.imul(value ^ value >>> 7, 61 | value) ^ value;
    return ((value ^ value >>> 14) >>> 0) / 4294967296;
  }

  function planetTexture(colors, craters) {
    var textureCanvas = document.createElement('canvas');
    textureCanvas.width = 512;
    textureCanvas.height = 256;
    var context = textureCanvas.getContext('2d');
    var y = 0;
    while (y < textureCanvas.height) {
      var height = 6 + random() * (craters ? 18 : 26);
      context.fillStyle = colors[Math.floor(random() * colors.length)];
      context.fillRect(0, y, textureCanvas.width, height);
      y += height;
    }
    for (var i = 0; i < (craters ? 38 : 75); i++) {
      var x = random() * textureCanvas.width;
      var cy = random() * textureCanvas.height;
      var radius = craters ? 3 + random() * 18 : 2 + random() * 5;
      context.fillStyle = 'rgba(0,0,0,' + (craters ? '0.26' : '0.12') + ')';
      context.beginPath();
      context.arc(x, cy, radius, 0, Math.PI * 2);
      context.fill();
      if (craters) {
        context.strokeStyle = 'rgba(255,255,255,0.2)';
        context.lineWidth = 1.5;
        context.stroke();
      }
    }
    var texture = new THREE.CanvasTexture(textureCanvas);
    texture.wrapS = THREE.RepeatWrapping;
    return texture;
  }

  var stars = new Float32Array(880 * 3);
  for (var star = 0; star < 880; star++) {
    stars[star * 3] = (random() - 0.5) * 26;
    stars[star * 3 + 1] = (random() - 0.5) * 16;
    stars[star * 3 + 2] = -4 - random() * 28;
  }
  var starGeometry = new THREE.BufferGeometry();
  starGeometry.setAttribute('position', new THREE.BufferAttribute(stars, 3));
  scene.add(new THREE.Points(starGeometry, new THREE.PointsMaterial({
    color: 0xe6e2da,
    size: 0.035,
    transparent: true,
    opacity: 0.8
  })));

  var planets = [];
  var planetSpecs = [
    {
      radius: 1.5, z: -7, nx: 0.82, ny: 0.8, speed: 0.05, phase: 0.4,
      colors: ['#c8a06a', '#b98a52', '#e0c08a', '#a67a45', '#d9b27a'], ring: true
    },
    {
      radius: 0.85, z: -5, nx: 0.06, ny: 0.42, speed: 0.07, phase: 2.1,
      colors: ['#9aa0a8', '#c9ced4', '#6d737b', '#e3e6ea', '#868c94'], glow: 0xd3d6db
    },
    {
      radius: 0.42, z: -3, nx: 0.9, ny: 0.2, speed: 0.09, phase: 4,
      colors: ['#87756b', '#a99585', '#665952', '#c4b7a7'], craters: true
    },
    {
      radius: 0.3, z: -13, nx: 0.3, ny: 0.07, speed: 0.06, phase: 5.2,
      colors: ['#4a9a7a', '#a9c4b0', '#2e6f55']
    }
  ];

  planetSpecs.forEach(function (spec) {
    var group = new THREE.Group();
    var body = new THREE.Mesh(
      new THREE.SphereGeometry(spec.radius, 48, 32),
      new THREE.MeshStandardMaterial({
        map: planetTexture(spec.colors, spec.craters),
        roughness: 0.92,
        metalness: 0
      })
    );
    group.add(body);
    if (spec.glow) {
      group.add(new THREE.Mesh(
        new THREE.SphereGeometry(spec.radius * 1.14, 32, 24),
        new THREE.MeshBasicMaterial({
          color: spec.glow,
          transparent: true,
          opacity: 0.14,
          side: THREE.BackSide,
          blending: THREE.AdditiveBlending,
          depthWrite: false
        })
      ));
    }
    if (spec.ring) {
      var ring = new THREE.Mesh(
        new THREE.PlaneGeometry(spec.radius * 5, spec.radius * 5),
        new THREE.MeshBasicMaterial({
          color: 0xc79a62,
          transparent: true,
          opacity: 0.25,
          side: THREE.DoubleSide,
          depthWrite: false
        })
      );
      ring.rotation.x = -1.2;
      group.add(ring);
      group.rotation.z = 0.38;
    }
    scene.add(group);
    planets.push({ group: group, body: body, spec: spec, pulse: 0 });
  });

  var pointer = { x: 0, y: 0 };
  function resize() {
    var width = window.innerWidth || 1;
    var height = window.innerHeight || 1;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    planets.forEach(function (planet) {
      var halfHeight = Math.tan(camera.fov * Math.PI / 360) * (camera.position.z - planet.spec.z);
      var scale = camera.aspect < 1 ? 0.62 : 1;
      planet.group.scale.setScalar(scale);
      planet.baseX = (planet.spec.nx - 0.5) * 2 * halfHeight * camera.aspect * 0.92;
      planet.baseY = (planet.spec.ny - 0.5) * 2 * halfHeight * 0.92;
    });
  }
  window.addEventListener('resize', resize);
  resize();

  var raycaster = new THREE.Raycaster();
  var pointerNdc = new THREE.Vector2();
  document.addEventListener('pointermove', function (event) {
    pointer.x = event.clientX / window.innerWidth * 2 - 1;
    pointer.y = event.clientY / window.innerHeight * 2 - 1;
  }, { passive: true });

  var press;
  document.addEventListener('pointerdown', function (event) {
    if (event.target.closest('a, button, input, label, form, .auth-card')) return;
    press = { x: event.clientX, y: event.clientY };
  });
  document.addEventListener('pointerup', function (event) {
    if (!press || Math.hypot(event.clientX - press.x, event.clientY - press.y) > 8) {
      press = null;
      return;
    }
    pointerNdc.set(event.clientX / window.innerWidth * 2 - 1, 1 - event.clientY / window.innerHeight * 2);
    raycaster.setFromCamera(pointerNdc, camera);
    var hit = raycaster.intersectObjects(planets.map(function (planet) { return planet.body; }))[0];
    if (hit) {
      planets.forEach(function (planet) {
        if (planet.body === hit.object) planet.pulse = 1;
      });
    }
    press = null;
  });

  var last = performance.now();
  function frame(now) {
    var dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    camera.position.x += (pointer.x * 0.45 - camera.position.x) * 0.025;
    camera.position.y += (-pointer.y * 0.35 - camera.position.y) * 0.025;
    camera.lookAt(0, 0, 0);
    planets.forEach(function (planet) {
      var spec = planet.spec;
      planet.group.position.set(
        planet.baseX + Math.sin(now / 1000 * spec.speed + spec.phase) * 0.4,
        planet.baseY + Math.cos(now / 1000 * spec.speed * 0.8 + spec.phase) * 0.3,
        spec.z
      );
      planet.body.rotation.y += dt * (reduce ? 0 : 0.035 + planet.pulse * 0.7);
      planet.pulse = Math.max(0, planet.pulse - dt * 1.6);
      planet.body.scale.setScalar(1 + planet.pulse * 0.22);
    });
    if (!reduce) {
      starGeometry.rotateZ(dt * 0.0015);
    }
    renderer.render(scene, camera);
    window.requestAnimationFrame(frame);
  }
  window.requestAnimationFrame(frame);
})();
