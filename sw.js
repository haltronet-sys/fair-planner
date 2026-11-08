const CACHE='faire-planner-v1';
const FILES=['./', 'index.html', 'trf-map.jpg', 'manifest.webmanifest', 'icons/icon-192.png', 'icons/icon-512.png', 'icons/maskable-512.png', 'icons/apple-touch-icon.png', 'fonts/AlegreyaSC-700-latin-ext.woff2', 'fonts/AlegreyaSC-700-latin.woff2', 'fonts/AlegreyaSans-400-latin-ext.woff2', 'fonts/AlegreyaSans-400-latin.woff2', 'fonts/AlegreyaSans-500-latin-ext.woff2', 'fonts/AlegreyaSans-500-latin.woff2', 'fonts/AlegreyaSans-700-latin-ext.woff2', 'fonts/AlegreyaSans-700-latin.woff2'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(FILES)).then(()=>self.skipWaiting()))});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim()))});
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  e.respondWith(caches.match(e.request,{ignoreSearch:true}).then(r=>r||fetch(e.request).catch(()=>caches.match('index.html'))));
});
