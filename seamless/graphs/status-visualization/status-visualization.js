// Adapted from Directed Graph Editor (Copyright (c) 2013 Ross Kirsling)
//  https://gist.github.com/rkirsling/5001347

// set up SVG for D3
//let width = parseFloat($("#graph").attr("width"));
//let height = parseFloat($("#graph").attr("height"));
let width = 1800;
let height = 1000; 

const svg = d3.select('body') 
  .select('svg')
  .on('contextmenu', () => { d3.event.preventDefault(); })
  .attr('width', width)
  .attr('height', height);

// set up initial nodes and links
//  - nodes are known by 'id', not by index in array.
//  - links are always source < target; edge directions are set by 'left' and 'right'.
let nodes = [
  { id: 0, name: "one", color: "red"},
  { id: 1, name: "two", color: "green"},
  { id: 2, name: "three", color: "blue"}
];
let links = [
  { source: nodes[0], target: nodes[1], left: false, right: true },
  { source: nodes[1], target: nodes[2], left: false, right: true }
];

// init D3 force layout
const force = d3.forceSimulation()
  .force('link', d3.forceLink().id((d) => d.id).distance(35))
  .force('charge', d3.forceManyBody().strength(-350))
  .force('x', d3.forceX(width / 2))
  .force('y', d3.forceY(height / 2))
  .on('tick', tick);

// init D3 drag support
const drag = d3.drag()
  // Mac Firefox doesn't distinguish between left/right click when Ctrl is held... 
  .filter(() => 1)
  .on('start', (d) => {
    if (!d3.event.active) force.alphaTarget(0.3).restart();

    d.fx = d.x;
    d.fy = d.y;
  })
  .on('drag', (d) => {
    d.fx = d3.event.x;
    d.fy = d3.event.y;
  })
  .on('end', (d) => {
    if (!d3.event.active) force.alphaTarget(0);

    d.fx = null;
    d.fy = null;
  });


radius = 15;

// define arrow markers for graph links
svg.append('svg:defs').append('svg:marker')
    .attr('id', 'end-arrow')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 12)
    .attr('markerWidth', 4)
    .attr('markerHeight', 4)
    .attr('orient', 'auto')
  .append('svg:path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', '#000');

svg.append('svg:defs').append('svg:marker')
    .attr('id', 'start-arrow')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 4)
    .attr('markerWidth', 3)
    .attr('markerHeight', 3)
    .attr('orient', 'auto')
  .append('svg:path')
    .attr('d', 'M10,-5L0,0L10,5')
    .attr('fill', '#000');

// handles to link and node element groups
let path = svg.append('svg:g').selectAll('path');
let circle = svg.append('svg:g').selectAll('g');

// mouse event vars
let selectedNode = null;
let selectedLink = null;

// update force layout (called automatically each iteration)
function tick() {
  circle.attr('cx', (d) => {
    return d.x = Math.max(radius, Math.min(width - radius, d.x)); 
  })
  .attr('cy', (d) => {
    return d.y = Math.max(radius, Math.min(height - radius, d.y)); 
  });
  
  // draw directed edges with proper padding from node centers
  path.attr('d', (d) => {
    const deltaX = d.target.x - d.source.x;
    const deltaY = d.target.y - d.source.y;
    const dist = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
    const normX = deltaX / dist;
    const normY = deltaY / dist;
    const sourcePadding = d.left ? 17 : 12;
    const targetPadding = d.right ? 17 : 12;
    function pad(v, norm, padding) {
      return (isFinite(v) && isFinite(norm)) ? v + padding * norm : 0
    }
    const sourceX = pad(d.source.x, normX, sourcePadding);
    const sourceY = pad(d.source.y, normY, sourcePadding);
    const targetX = pad(d.target.x, normX, -targetPadding);
    const targetY = pad(d.target.y, normY, -targetPadding);

    return `M${sourceX},${sourceY}L${targetX},${targetY}`;
  });

  circle.attr('transform', (d) => `translate(${d.x},${d.y})`);
}

function selectNode(node) {
  status = node.status ? node.status : "None"
  $("#error_message").text(status)
}

// update graph (called when needed)
function restart() {
  // path (link) group
  path = path.data(links);

  // update existing links
  path.classed('selected', (d) => d === selectedLink)
    .style('marker-start', (d) => d.left ? 'url(#start-arrow)' : '')
    .style('marker-end', (d) => d.right ? 'url(#end-arrow)' : '');

  // remove old links
  path.exit().remove();

  // add new links
  path = path.enter().append('svg:path')
    .attr('class', 'link')
    .classed('selected', (d) => d === selectedLink)
    .style('marker-start', (d) => d.left ? 'url(#start-arrow)' : '')
    .style('marker-end', (d) => d.right ? 'url(#end-arrow)' : '')
    .on('mousedown', (d) => {
      // select link
      selectedLink = (d === selectedLink) ? null : d;
      selectedNode = null;
      restart();
    })
    .merge(path);

  // circle (node) group
  // NB: the function arg is crucial here! nodes are known by id, not by index!
  circle = circle.data(nodes, (d) => d.id);

  function style_circle(d) {
    d
    //.style('fill', (d) => (d === selectedNode) ? d3.rgb(colors(d.id)).brighter().toString() : colors(d.id))    
    .style('fill', (d) => d.color)
    .style('stroke', "black")
    .style('stroke-width', (d) => (d === selectedNode) ? 2.5 : 1.5)
    .attr('transform', (d) => (d === selectedNode) ? 'scale(1.2)' : '')
    .attr('r', radius)
    ;
    return d
  }

  // update existing nodes (selected visual states)
  circle.selectAll('circle')
    .call(style_circle)    

  // remove old nodes
  circle.exit().remove();

  // add new nodes
  const g = circle.enter().append('svg:g');
  
  g.append('svg:circle')
    .attr('class', 'node')    
    .call(style_circle)
    .on('mouseover', function (d) {
      // enlarge target node
      d3.select(this).attr('transform', 'scale(1.1)');
    })
    .on('mouseout', function (d) {
      if (d === selectedNode) return;
      // unenlarge target node
      d3.select(this).attr('transform', '');
    })
    .on('mousedown', (d) => {

      // select node      
      selectedNode = (d === selectedNode) ? null : d;
      selectNode(d)
      selectedLink = null;
      restart();
    })

  // show node IDs
  g.append('svg:text')
    .attr('x', 0)
    .attr('y', 4)
    .attr('class', 'id')
    .text((d) => d.name);

  circle = g.merge(circle);

  // set the graph in motion
  force
    .nodes(nodes)
    .force('link').links(links);

  force.alphaTarget(0.3).restart();
  circle.call(drag);
}

function spliceLinksForNode(node) {
  const toSplice = links.filter((l) => l.source === node || l.target === node);
  for (const l of toSplice) {
    links.splice(links.indexOf(l), 1);
  }
}

// only respond once per keydown
let lastKeyDown = -1;

function keydown() {
  d3.event.preventDefault();

  if (lastKeyDown !== -1) return;
  lastKeyDown = d3.event.keyCode;

  if (!selectedNode && !selectedLink) return;

  switch (d3.event.keyCode) {
      //...
  }  
}

// app starts here
d3.select(window)
  .on('keydown', keydown)
restart();
// END OF Directed Graph Editor

// START of config block
// The code below may be replaced if the ports and graph namespaces are different

SEAMLESS_UPDATE_PORT=null  //5138, but will be 80 or 8080 if the page is served under that port
SEAMLESS_REST_PORT=null    //the same as where the page will be served under 
SEAMLESS_SHARE_NAMESPACE="status"
// END of config block

ctx = connect_seamless(
  SEAMLESS_UPDATE_PORT,
  SEAMLESS_REST_PORT,
  SEAMLESS_SHARE_NAMESPACE
);
ctx.self.onsharelist = function(sharelist) {
  ctx.vis_status.onchange = function() {
    data = ctx.vis_status.value
    graph = JSON.parse(data)
    //$("#model").text(data)
    newNodes = []
    graph.nodes.forEach( (shareNode) => {
      let matchingNode = null
      for (i=0; i < nodes.length; i++){
        node = nodes[i]
        if (node.name == shareNode.name) {
          matchingNode = node
          break
        }
      }
      newNode = matchingNode      
      if (newNode === null) {
        newNode = {
          name: shareNode.name,
          id: newNodes.length
        }
      }
      newNode.color = shareNode.color
      newNode.status = shareNode.status
      newNodes.push(newNode)
    })
    nodeMapping = {}
    newNodes.forEach((newNode) => {
      nodeMapping[newNode.id] = newNode
    })
    newLinks = []
    graph.connections.forEach( (shareLink) => {
      newLink = {
        source: nodeMapping[shareLink.source],
        target: nodeMapping[shareLink.target],
        right: true, 
      }
      newLink.left = (shareLink.type == "link")
      newLinks.push(newLink)
    }) 
    newSelectedNode = null
    if (selectedNode) {
      for (i=0; i < newNodes.length; i++){
        node = newNodes[i]
        if (node.name == selectedNode.name) {
          newSelectedNode = node
          break
        }
      }
    }
    nodes = []
    links = []
    selectedNode = null
    selectedLink = null
    restart()
    
    nodes = newNodes
    links = newLinks
    selectedNode = newSelectedNode
    if (selectedNode) {
      selectNode(selectedNode)      
    }
    restart()  
  }
}
 
