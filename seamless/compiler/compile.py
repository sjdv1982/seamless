from . import compilers, languages

def compile(moduletree):
    """Takes a JSON dict of source object definitions (source code strings, language
    property, compiler options, etc.)
     and generates a dict-of-binary-objects (.o / .obj)
    Linking options etc. are passed through.
    This dict can be sent to a transformer or reactor over a binarymodule pin"""
    for modulename, module in moduletree.items():
        lang = module["language"]
        language = languages[lang]
        compiler_name = module.get("compiler", languages.get("compiler"))
        assert compiler_name is not None, lang
        compiler = compilers[compiler_name]
        target = module.get("target", "profile")
        assert target in ("release", "debug", "profile"), target
        options = module.get("options")
        if options is None:
            if target in ("release", "profile"):
                options = compiler["options"]
