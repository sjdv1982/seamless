import sys
count = 0
for l in open(sys.argv[1]):
    l = l.strip()
    if l == "#" + str(count + 1):
        count +=1
print(count)
