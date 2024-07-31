
// Create NGL Stage object
var stage = new NGL.Stage("viewport");

// Handle window resizing
window.addEventListener("resize", function (event) {
  stage.handleResize();
}, false);


pdb = null

ctx = connect_seamless()
ctx.self.onsharelist = function(sharelist) {
  ctx["pdb0.pdb"].auto_read = true
  ctx["filtered_pdb.pdb"].auto_read = true
  ctx["pdb.pdb"].auto_read = true
  ctx["representation.js"].auto_read = true
  ctx["filter_code.bash"].auto_read = true
  ctx["code.bash"].auto_read = true

  reload = function() {
    if (!this.initial) location.reload()
  }
  ctx["index.html"].onchange = reload
  ctx["vismol.js"].onchange = reload

  document.getElementById("representation").onchange = function() {
    ctx["representation.js"].set(this.value)
    loadNGL()
  }

  const inputElement = document.getElementById("pdbfile");
  inputElement.addEventListener("change", upload_pdb, false);
  function upload_pdb() {
    const file = this.files[0]
    if (file === undefined) return
    file.text().then(function(text){
      ctx["pdb0.pdb"].set(text)  
    })

  }

  ctx["representation.js"].onchange = function() {
    value = this.value
    document.getElementById("representation").value = value
  }


  document.getElementById("code").onchange = function() {
    ctx["code.bash"].set(this.value)
    loadNGL()
  }
  ctx["code.bash"].onchange = function() {
    value = this.value
    document.getElementById("code").value = value
  }

  document.getElementById("filter_code").onchange = function() {
    ctx["filter_code.bash"].set(this.value)
    loadNGL()
  }
  ctx["filter_code.bash"].onchange = function() {
    value = this.value
    document.getElementById("filter_code").value = value
  }

  ctx.self.onchange = function() {    
    loadNGL()
  }
}

function loadNGL() {
  stage.removeAllComponents()  
  Promise.all([    
    stage.loadFile("./pdb0.pdb"),
    stage.loadFile("./filtered_pdb.pdb"),
    stage.loadFile("./pdb.pdb")
  ]).then(function (l) {
    rep = ctx["representation.js"]
    if (rep === undefined) return    
    pdb0 = l[0]
    filtered_pdb = l[1]
    pdb = l[2]
    eval(rep.value)
    stage.autoView()
    first = false
  })
}
loadNGL()
