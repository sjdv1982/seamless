result = []
colors2 = colors.splitlines()
clust = [[int(vv) for vv in v.split()[3:]] for v in clusters.splitlines() ]
for cnr, c in enumerate(clust):
    colnr = cnr%len(colors2)
    color = colors2[colnr]
    result.append({
        "name": 'Cluster %d' % (cnr+1),
        "type": 'scatter',
        "mode": 'markers',
      	"marker": {
          "color": color,
          "size": 7
      	},
        "textfont": {
          "size": 50
        },
      }
    )
    result.append({
        "showlegend": False,
        "mode": 'markers',
      	"marker": {
          "color": color,
          "symbol": 'triangle-up',
          "size": 15
        }
    })
return result
