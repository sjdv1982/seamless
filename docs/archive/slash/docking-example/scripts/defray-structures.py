import sys
mode = 0
count = 0
length = 0
store = []
nstruc = 0

def print_struc():
    if len(store) != count:
        sys.exit()
    if len(store[-1].split()) != length:
        sys.exit()
    for l in store:
        print(l)
    store[:] = []

for l in open(sys.argv[1]):
    l = l.strip()
    if mode == 0 and l == "#1":
        mode = 1
        count = 1
    elif mode == 1:
        if l == "#2":
            mode = 2
            nstruc = 2
        else:
            count += 1
            length = len(l.split())
    if mode < 2:
        print(l)
    else:
        if l == "#" + str(nstruc + 1):
            print_struc()
            nstruc += 1
        store.append(l)
print_struc()
