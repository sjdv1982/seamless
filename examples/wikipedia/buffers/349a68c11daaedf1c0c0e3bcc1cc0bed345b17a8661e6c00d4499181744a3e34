import sys
import re
import xml.etree.ElementTree as ET

abstracts_file = sys.argv[1]

vowels = re.compile("[aeiou]")
count = 0
for event, elem in ET.iterparse(abstracts_file, events=["end"]):
    try:
        if elem.tag != "abstract":
            continue
        text = elem.text
        if text is None:
            continue
        if text.startswith("|"):
            continue
        count += len(re.findall(vowels, text))
    finally:
        elem.clear()

print(count)
