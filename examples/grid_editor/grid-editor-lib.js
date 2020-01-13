var grid_area = d3.select("#grid_area")
  .select("svg")
  
svg_height = parseInt(grid_area.attr("height"))

function unpack_grid_data(grid_data) {
  mydata = []
  grid_data.split("\n").reverse().forEach(l => {
      row = []
      l.split(" ").forEach(ll => {
        if (ll.length) {
          obj = [parseInt(ll[0]), parseInt(ll[1])]      
          row.push(obj)
        }
      })
      if (row.length) mydata.push(row)
  })
  return mydata
}

function pack_grid_data(grid_table) {
  g = ""
  grid_table.slice().reverse().forEach(row => {      
      row.forEach(square => {
        g += square[0].toString() + square[1].toString() + " ";
      })
      g += "\n"
  })
  return g
}

function draw_grid(grid_area, grid_table, params, edit_callback, edit_params) {

  tx = params.trans_x
  if (!tx) tx = 0
  ty = params.trans_y
  if (!ty) ty = 0  
  dx = params.offset_x + params.square_size * tx;
  dy = params.offset_y + params.square_size * ty;
  dy = svg_height - dy
  grid_area
    .attr("transform", `translate(${dx},${dy}) scale(1,-1)`)


  rows = grid_table.length
  cols = grid_table[0].length

  var grid = grid_area.selectAll(".row")
    .remove()
  ;
  
  var grid = grid_area.selectAll(".row")
    .remove()
    .data(grid_table)    
  ;
  
  click = function(d, i) {
    if (edit_params.step1 == 0) {
      d[1] += edit_params.step2;
      if (d[1] > edit_params.max2) d[1] = 0;
    }      
    else {
      d[0] += edit_params.step1;
      if (d[0] > edit_params.max1) {
        d[0] = 0;
        d[1] += edit_params.step2;
        if (d[1] > edit_params.max2 ) d[1] = 0;
      }
    }
    edit_callback()
  }
    
  grid
    .enter().append("g")
    .merge(grid)
    .attr("class", "row")
    .each(function(drow, y){
      row = d3.select(this)
        .selectAll(".square")
        .data(drow)
      ;
      row
        .enter().append("g")
        .merge(row)
        .attr("class", "square")
        .each(function(dsquare, x){
          square_size = params.square_size
          cls1 = "rect"
          cls1 += " val" + dsquare[0]
          cls2 = "circle"
          cls2 += " val" + dsquare[1]
          sele = d3.select(this)
            .append("rect")
            .attr("class", cls1)
            .attr("width", square_size)
            .attr("height", square_size)
            .attr("x", square_size * x)
            .attr("y", square_size * y);
          if (typeof(edit_callback) !== "undefined") {
            sele
              .on("click",click);
          }
          sele = d3.select(this)
            .append("circle")
            .attr("class", cls2)
            .attr("cx", square_size * (x+0.5))
            .attr("cy", square_size * (y+0.5));
            if (typeof(edit_callback) !== "undefined") {
              sele
                .on("click",click);
            }
         })
         .exit()
         .remove()
      ;
    })
    .exit()
    .remove()
  ;
}
