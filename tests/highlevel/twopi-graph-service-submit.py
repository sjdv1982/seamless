ADDRESS = '127.0.0.1'
PORT = 8700

import requests, sys, json

infile, outfile = sys.argv[1:]
graph = json.load(open(infile))

response = requests.get('http://{0}:{1}'.format(ADDRESS, PORT),data=json.dumps(graph))
colored_graph = response.json()

with open(outfile, "w") as f:
    json.dump(colored_graph, f, indent=2, sort_keys=True)