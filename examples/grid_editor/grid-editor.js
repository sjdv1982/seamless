grid_data1 = `
 00 10 10 10 00
 10 11 01 11 10
 00 10 10 10 00
`

grid_data2 = `
 00 00 02 00 00
 00 02 02 02 02
 00 00 02 02 00
`

params1 = {
  square_size: 40,
  offset_x: 30,
  offset_y: 200,
}

params2 = {
  square_size: 40,
  offset_x: 300,
  offset_y: 200,
}

params3 = {
  square_size: 40,
  offset_x: 750,
  offset_y: 200,
}

params4 = {
  square_size: 40,
  offset_x: 750,
  offset_y: 200,
  trans_x: 1,
  trans_y: -1
}

edit_params1 = {
  step1: 1,
  step2: 1,
  max1: 1,
  max2: 1
}

edit_params2 = {
  step1: 0,
  step2: 2,
  max1: 0,
  max2: 2
}

var grid_area1 = grid_area
  .append("g")

var grid_area2 = grid_area
  .append("g")

var grid_area3 = grid_area
  .append("g")

var grid_area4 = grid_area
  .append("g")

grid_table1 = unpack_grid_data(grid_data1)
grid_table2 = unpack_grid_data(grid_data2)

ctx = connect_seamless()
ctx.self.onsharelist = function(sharelist) {
    ctx.combined_grid_params.onchange = function() {
        grid_params = JSON.parse(ctx.combined_grid_params.value)
        params1 = grid_params.grid_params[0]
        params2 = grid_params.grid_params[1]
        params3 = grid_params.grid_params[2]
        params4 = grid_params.grid_params[3]
        edit_params1 = grid_params.edit_params[0]
        edit_params2 = grid_params.edit_params[1]
        draw()
    }
    ctx.grid_data1.onchange = function() {
        grid_data1 = ctx.grid_data1.value
        grid_table1 = unpack_grid_data(grid_data1)
        draw()
    }
    ctx.grid_data2.onchange = function() {
      grid_data2 = ctx.grid_data2.value
      grid_table2 = unpack_grid_data(grid_data2)
      draw()
    }
    function reload() {
      if (!this.initial) location.reload()
    }
    ctx["grid-editor.html"].onchange = reload
    ctx["grid-editor.js"].onchange = reload
}

function update_trans(){
  j = JSON.stringify([params4.trans_x, params4.trans_y])
  ctx.translation.set(j)
  draw()
}

d3.select("#trans_x")
  .on("change", function(){
    params4.trans_x = parseInt(this.value)
    update_trans()
  })
d3.select("#trans_y")  
  .on("change", function(){
    params4.trans_y = parseInt(this.value)
    update_trans()
  })

function draw() {
  function edit_callback1() { 
    grid_data1 = pack_grid_data(grid_table1)
    ctx.grid_data1.set(grid_data1)
    draw()
  }
  function edit_callback2() { 
    grid_data2 = pack_grid_data(grid_table2)
    ctx.grid_data2.set(grid_data2)
    draw()
  }
  draw_grid(grid_area1, grid_table1, params1, edit_callback1, edit_params1)
  draw_grid(grid_area2, grid_table2, params2, edit_callback2, edit_params2)
  draw_grid(grid_area3, grid_table1, params3)
  draw_grid(grid_area4, grid_table2, params4)
}


draw()
