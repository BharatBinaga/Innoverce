(function () {
  var canvas = document.getElementById('space');
  if (!canvas || !window.THREE) return;

  var renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  } catch (error) {
    canvas.style.display = 'none';
    return;
  }

  var fov = 50;
  var cameraZ = 12;
  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(fov, 1, 0.1, 200);
  camera.position.set(0, 0, cameraZ);
  scene.add(new THREE.AmbientLight(0x80808a, 0.6));
  var sun = new THREE.DirectionalLight(0xffe6c4, 1.6);
  sun.position.set(-7, 5, 8);
  scene.add(sun);

  function rng(seed) {
    return function () {
      seed |= 0;
      seed = seed + 0x6D2B79F5 | 0;
      var value = Math.imul(seed ^ seed >>> 15, 1 | seed);
      value = value + Math.imul(value ^ value >>> 7, 61 | value) ^ value;
      return ((value ^ value >>> 14) >>> 0) / 4294967296;
    };
  }

  function viewHalf(z) {
    var height = Math.tan(fov * Math.PI / 360) * (cameraZ - z);
    return { width: height * camera.aspect, height: height };
  }

  function makeCanvas(width, height) {
    var result = document.createElement('canvas');
    result.width = width;
    result.height = height;
    return result;
  }

  function bandTexture(colors, seed) {
    var textureCanvas = makeCanvas(512, 256);
    var context = textureCanvas.getContext('2d');
    var random = rng(seed);
    var y = 0;
    while (y < 256) {
      var bandHeight = 6 + random() * 26;
      context.fillStyle = colors[Math.floor(random() * colors.length)];
      context.fillRect(0, y, 512, bandHeight);
      y += bandHeight;
    }
    for (var line = 0; line < 70; line++) {
      context.fillStyle = random() > 0.5 ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.14)';
      context.fillRect(0, random() * 256, 512, 1 + random() * 3);
    }
    for (var cloud = 0; cloud < 14; cloud++) {
      context.fillStyle = 'rgba(255,255,255,0.08)';
      context.beginPath();
      context.ellipse(random() * 512, random() * 256, 10 + random() * 40, 2 + random() * 5, 0, 0, 6.283);
      context.fill();
    }
    return new THREE.CanvasTexture(textureCanvas);
  }

  function craterTexture(base, seed) {
    var textureCanvas = makeCanvas(512, 256);
    var context = textureCanvas.getContext('2d');
    var random = rng(seed);
    context.fillStyle = base;
    context.fillRect(0, 0, 512, 256);
    for (var mark = 0; mark < 500; mark++) {
      context.fillStyle = (random() > 0.5 ? 'rgba(255,255,255,' : 'rgba(0,0,0,') + (0.03 + random() * 0.07) + ')';
      context.fillRect(random() * 512, random() * 256, 2 + random() * 6, 2 + random() * 6);
    }
    for (var crater = 0; crater < 46; crater++) {
      var x = random() * 512;
      var y = random() * 256;
      var radius = 4 + random() * 20;
      context.fillStyle = 'rgba(0,0,0,0.28)';
      context.beginPath();
      context.arc(x, y, radius, 0, 6.283);
      context.fill();
      context.strokeStyle = 'rgba(255,255,255,0.18)';
      context.lineWidth = 1.5;
      context.beginPath();
      context.arc(x - 1, y - 1, radius, 0, 6.283);
      context.stroke();
    }
    return new THREE.CanvasTexture(textureCanvas);
  }

  function ringTexture() {
    var textureCanvas = makeCanvas(512, 512);
    var context = textureCanvas.getContext('2d');
    var random = rng(4);
    for (var radius = 130; radius < 256; radius += 2) {
      var fraction = radius / 256;
      if (fraction > 0.78 && fraction < 0.82) continue;
      context.strokeStyle = 'rgba(' + (210 + random() * 30 | 0) + ',' +
        (176 + random() * 30 | 0) + ',' + (125 + random() * 30 | 0) + ',' +
        (0.18 + random() * 0.5) + ')';
      context.lineWidth = 2.2;
      context.beginPath();
      context.arc(256, 256, radius, 0, 6.283);
      context.stroke();
    }
    return new THREE.CanvasTexture(textureCanvas);
  }

  var dotCanvas = makeCanvas(32, 32);
  var dotContext = dotCanvas.getContext('2d');
  var dotGradient = dotContext.createRadialGradient(16, 16, 0, 16, 16, 16);
  dotGradient.addColorStop(0, 'rgba(255,255,255,1)');
  dotGradient.addColorStop(0.35, 'rgba(255,255,255,0.55)');
  dotGradient.addColorStop(1, 'rgba(255,255,255,0)');
  dotContext.fillStyle = dotGradient;
  dotContext.fillRect(0, 0, 32, 32);
  var dotTexture = new THREE.CanvasTexture(dotCanvas);
  var random = rng(99);
  var layers = [
    { count: 520, z: -26, size: 0.19, speed: 0.12, color: 0xdad7d0, opacity: 0.78 },
    { count: 260, z: -16, size: 0.18, speed: 0.28, color: 0xf0ece4, opacity: 0.92 },
    { count: 100, z: -8, size: 0.16, speed: 0.55, color: 0xffe2b8, opacity: 1 }
  ];

  layers.forEach(function (layer) {
    layer.positions = new Float32Array(layer.count * 3);
    layer.geometry = new THREE.BufferGeometry();
    layer.geometry.setAttribute('position', new THREE.BufferAttribute(layer.positions, 3));
    layer.material = new THREE.PointsMaterial({
      color: layer.color, size: layer.size, map: dotTexture, transparent: true,
      opacity: layer.opacity, depthWrite: false, sizeAttenuation: true
    });
    layer.points = new THREE.Points(layer.geometry, layer.material);
    layer.points.frustumCulled = false;
    scene.add(layer.points);
  });

  function layoutStars() {
    layers.forEach(function (layer) {
      var bounds = viewHalf(layer.z);
      layer.halfWidth = bounds.width + 1;
      layer.halfHeight = bounds.height + 1;
      for (var index = 0; index < layer.count; index++) {
        layer.positions[index * 3] = (random() * 2 - 1) * layer.halfWidth;
        layer.positions[index * 3 + 1] = (random() * 2 - 1) * layer.halfHeight;
        layer.positions[index * 3 + 2] = layer.z + (random() - 0.5) * 2;
      }
      layer.geometry.attributes.position.needsUpdate = true;
    });
  }

  var planets = [
    { texture: bandTexture(['#c8a06a', '#b98a52', '#e0c08a', '#a67a45', '#d9b27a'], 3), radius: 1.5, z: -7, x: 0.82, y: 0.8, ring: true, ax: 0.5, ay: 0.3, speed: 0.05, phase: 0.4, spin: 0.03, parallax: 1.4 },
    { texture: bandTexture(['#9aa0a8', '#c9ced4', '#6d737b', '#e3e6ea', '#868c94'], 8), radius: 0.85, z: -5, x: 0.06, y: 0.42, glow: 0xd3d6db, ax: 0.4, ay: 0.35, speed: 0.07, phase: 2.1, spin: 0.05, parallax: 2.0 },
    { texture: craterTexture('#7a6a62', 5), radius: 0.42, z: -3, x: 0.9, y: 0.2, ax: 0.25, ay: 0.3, speed: 0.09, phase: 4.0, spin: 0.08, parallax: 2.8 },
    { texture: bandTexture(['#4a9a7a', '#a9c4b0', '#2e6f55'], 12), radius: 0.3, z: -13, x: 0.3, y: 0.07, ax: 0.3, ay: 0.2, speed: 0.06, phase: 5.2, spin: 0.04, parallax: 0.8 }
  ];

  planets.forEach(function (planet) {
    planet.group = new THREE.Group();
    planet.body = new THREE.Mesh(
      new THREE.SphereGeometry(planet.radius, 48, 32),
      new THREE.MeshStandardMaterial({ map: planet.texture, roughness: 0.92, metalness: 0 })
    );
    planet.group.add(planet.body);
    if (planet.glow) {
      planet.group.add(new THREE.Mesh(
        new THREE.SphereGeometry(planet.radius * 1.14, 32, 24),
        new THREE.MeshBasicMaterial({
          color: planet.glow, transparent: true, opacity: 0.14, side: THREE.BackSide,
          blending: THREE.AdditiveBlending, depthWrite: false
        })
      ));
    }
    if (planet.ring) {
      var ring = new THREE.Mesh(
        new THREE.PlaneGeometry(planet.radius * 5, planet.radius * 5),
        new THREE.MeshBasicMaterial({
          map: ringTexture(), transparent: true, opacity: 0.7,
          side: THREE.DoubleSide, depthWrite: false
        })
      );
      ring.rotation.x = -1.2;
      planet.group.add(ring);
      planet.group.rotation.z = 0.38;
    }
    scene.add(planet.group);
  });

  function layoutPlanets() {
    var scale = camera.aspect < 1 ? 0.62 : 1;
    planets.forEach(function (planet) {
      var bounds = viewHalf(planet.z);
      planet.baseX = (planet.x - 0.5) * 2 * bounds.width * 0.92;
      planet.baseY = (planet.y - 0.5) * 2 * bounds.height * 0.92;
      planet.group.scale.setScalar(scale);
    });
  }

  function resize() {
    var width = canvas.clientWidth || 1;
    var height = canvas.clientHeight || 1;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    layoutStars();
    layoutPlanets();
  }

  resize();
  window.addEventListener('resize', resize);
  var previous = performance.now();
  function animate(now) {
    var elapsed = Math.min((now - previous) / 1000, 0.05);
    previous = now;
    var scrollRange = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    var scrollProgress = Math.min(1, Math.max(0, window.scrollY / scrollRange));
    layers.forEach(function (layer) {
      for (var index = 0; index < layer.count; index++) {
        var position = index * 3;
        layer.positions[position] -= layer.speed * elapsed;
        if (layer.positions[position] < -layer.halfWidth) {
          layer.positions[position] = layer.halfWidth;
          layer.positions[position + 1] = (Math.random() * 2 - 1) * layer.halfHeight;
        }
      }
      layer.geometry.attributes.position.needsUpdate = true;
      layer.material.opacity = layer.opacity * (0.85 + 0.15 * Math.sin(now / 1000 * (0.4 + layer.speed) + layer.z));
    });
    planets.forEach(function (planet) {
      planet.body.rotation.y += planet.spin * elapsed;
      planet.group.position.set(
        planet.baseX + Math.sin(now / 1000 * planet.speed + planet.phase) * planet.ax,
        planet.baseY + Math.cos(now / 1000 * planet.speed * 0.8 + planet.phase) * planet.ay +
          (scrollProgress - 0.5) * planet.parallax,
        planet.z
      );
    });
    renderer.render(scene, camera);
    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
})();
