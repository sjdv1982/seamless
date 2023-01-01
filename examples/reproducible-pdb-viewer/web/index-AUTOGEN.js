app_globals = {}

ngl_stages = {}

function load_ngl(stage_id, pdbs, representations, format){
    if (Object.keys(pdbs).length === 0) return;

    var stage = ngl_stages[stage_id]
    if (typeof stage === 'null' || typeof stage === 'undefined'){
        var stage = new NGL.Stage(stage_id)
        ngl_stages[stage_id] = stage
    }
    stage.removeAllComponents()
    var pdbs2 = pdbs
    if (typeof pdbs === "string") {
        var pdbs2 = {"DEFAULT": pdbs}
    }
    Object.keys(pdbs2).forEach(function(item){
        let pdb = new Blob([pdbs2[item]], {type : 'text/plain'})
        let ext = item.slice((item.lastIndexOf(".") - 1 >>> 0) + 2);
        if (ext == "") ext = format;
        stage.loadFile(pdb, { ext: ext } ).then(function (o) {            
            let curr_representations = representations[item]
            if (curr_representations === null || curr_representations === undefined) curr_representations = representations["DEFAULT"]
            if (curr_representations === null || curr_representations === undefined) return
            if (!Array.isArray(curr_representations)) curr_representations = [curr_representations]
            Object.keys(curr_representations).forEach(function(repnr){
                let rep = curr_representations[repnr]
                o.addRepresentation(rep["type"], {...rep["params"]})
            })
            o.autoView();
        })        
    })
}



seamless_read_paths = {
  "text": [
    "representation",
    "nglviewer_1__structures.json"
  ],
  "json": [
    "bigselect_1__selected.json",
    "bigselect_1__options.json",
    "nglviewer_1__representation.json"
  ]
}
seamless_write_paths = {
  "text": [
    "representation"
  ],
  "json": [
    "bigselect_1__selected.json"
  ]
}
seamless_auto_read_paths = [
  "representation",
  "bigselect_1__selected.json",
  "bigselect_1__options.json",
  "nglviewer_1__structures.json",
  "nglviewer_1__representation.json"
]
seamless_path_to_cell = {
  "bigselect_1__selected.json": "pdb_code",
  "bigselect_1__options.json": "pdb_codes",
  "nglviewer_1__structures.json": "pdb_structure",
  "nglviewer_1__representation.json": "representation3"
}

ctx = connect_seamless()
ctx.self.onsharelist = function (sharelist) {
  sharelist.forEach(path0 => {
    let path = path0.replaceAll("/", "__")
    cell0 = seamless_path_to_cell[path]
    if (cell0 === undefined) cell0 = path0
    let cell = cell0.replaceAll("/", "__")
    if (ctx[path].binary) {
      ctx[path].onchange = function () {
        content_type = ctx[path].content_type
        if (content_type === null) content_type = ""
        const v = new Blob([this.value], {type: content_type})
        vm[cell].value = v
        vm[cell].checksum = this.checksum
      }
    }
    else if (seamless_read_paths["json"].indexOf(path) >= 0) {
      ctx[path].onchange = function () {
        try {
          const v = JSON.parse(this.value)
          vm[cell].value = v
          vm[cell].checksum = this.checksum
        }
        catch (error) {
          console.log(`Cannot parse server value of cell '${cell}' as JSON`)
        }
      }
    }
    else if (seamless_read_paths["text"].indexOf(path) >= 0) {
      ctx[path].onchange = function () {
        vm[cell].value = this.value
        vm[cell].checksum = this.checksum
      }
    }

    if (seamless_auto_read_paths.indexOf(path) >= 0) {
      ctx[path].auto_read = true
    }
  })
}
webctx = connect_seamless(null, null, share_namespace="status")
webctx.self.onsharelist = function (sharelist) {
  vis_status = webctx["vis_status"]
  if (!(vis_status === undefined)) {
    vis_status.onchange = function() {      
      let jstatus = JSON.parse(vis_status.value)
      cells = {}
      transformers = {}
      jstatus.nodes.forEach(node => {
        if (node.type == "cell") {
          cells[node.name] = node
        }
        else if (node.type == "transformer") {
          transformers[node.name] = node
        }
      })
      jstatus.cells = cells
      jstatus.transformers = transformers
      vm["STATUS"].value = jstatus
      vm["STATUS"].checksum = vis_status.checksum
    }
  }
}  

function seamless_update(path, value, encoding) {
  if (!ctx) return
  if (!ctx.self.sharelist) return
  if (ctx.self.sharelist.indexOf(path.replaceAll("__", "/")) < 0) return
  if (ctx[path].binary) {
    ctx[path].set(value)
  }
  else if (encoding == "json") {
    ctx[path].set(JSON.stringify(value))
  }
  else if (encoding == "text") {
    ctx[path].set(value)
  }
}


const app = new Vue({
  vuetify: new Vuetify(),
  data() {
    return {
      ...{
        "representation": {
          "checksum": null,
          "value": ""
        },
        "pdb_code": {
          "checksum": null,
          "value": ""
        },
        "pdb_codes": {
          "checksum": null,
          "value": []
        },
        "pdb_structure": {
          "checksum": null,
          "value": ""
        },
        "representation3": {
          "checksum": null,
          "value": {}
        },
        "bigselect_1_input": {
          "value": ""
        }
      }, 
      ...{
        "STATUS": {
          "checksum": null,
          "value": {}
        }
      }
    }
  },
  methods: {
    METHOD_get_app_globals() {
      return app_globals
    },
    METHOD_file_upload(cellname, file) { 
      if (file === undefined) return
      that = this
      file.arrayBuffer().then(function(buf){
        that[cellname].value = new Blob([new Uint8Array(buf)], {type: file.type })
      })  
    }
    
  },
  watch: {
    "pdb_structure.value": function(){ load_ngl("nglviewer_1",this.pdb_structure.value,this.representation3.value,"cif") },
    "representation3.value": function(){ load_ngl("nglviewer_1",this.pdb_structure.value,this.representation3.value,"cif") },
    "representation.value": function (value) {
      seamless_update("representation", value, "text")
    },
    "pdb_code.value": function (value) {
      seamless_update("bigselect_1__selected.json", value, "json")
    },
  },
  updated() {

  }
})

vm = app.$mount('#app')
