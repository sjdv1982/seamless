# Copyright 2007-2016, Sjoerd de Vries


def macro_enum(name, content):
    if not name.startswith("Enum"):
        return

    bracket_depth = 0
    start = -1
    end = -1

    for i, char in enumerate(content):
        if char.isalnum() or char == "_":
            continue

        if char == "(":
            if bracket_depth == 0:
                start = i

            bracket_depth += 1

        elif char == ")":
            if bracket_depth == 0:
                raise Exception("Compile error: invalid Enum member statement %s" % (name + " " + content))

            bracket_depth -= 1
            if bracket_depth == 0:
                end = i
                break

        elif bracket_depth == 0:
            raise Exception("Compile error: invalid Enum member statement %s" % (name + " " + content))

    if start == -1 or end == -1:
        raise Exception("Compile error: invalid Enum member statement %s" % (name + " " + content))

    name, enums = content[:start], content[start+1:end]
    if enums.find(",") == -1:
        enums += ","

    args_string = "(" + enums + ")"
    result = "String " + name + content[end+1:]
    result += "\nvalidate {\n  if %s is not None: assert %s in %s\n}\nform {\n  %s.options = %s\n}\n" %  \
              (name, name, args_string, name, args_string[1:-1])
    return result

