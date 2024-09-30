import seamless

seamless.delegate(level=3)

from seamless import Checksum, transformer

abstracts = Checksum.load("enwiki-latest-abstract.xml")
# abstracts = Checksum("c953f648215413c5c7a3ae179a57d74e5ca495290a8e5a06a474baa158178d15")
# abstracts = Checksum("da0774f46efed72c7c20ba0133716bc0d7f7e3ae7c7531f0da7fc60deefbb07a")


@transformer(return_transformation=True)
def count_vowels(abstracts):
    import re
    import xml.etree.ElementTree as ET
    from io import BytesIO

    abstracts_reader = BytesIO(abstracts)

    vowels = re.compile("[aeiou]")
    count = 0
    for event, elem in ET.iterparse(abstracts_reader, events=["end"]):
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

    return count


count_vowels.celltypes.abstracts = "bytes"

transformation = count_vowels(abstracts)
print(transformation.as_checksum())
transformation.compute()
print(transformation.exception)
print(transformation.logs)
print(transformation.value)


# checksum: 2d0b075213f2ffad87d159c4ddabf11dd6fcf3c1d343d793629a71f027471e8c

# About 165s when uploaded (all of it execution time)
