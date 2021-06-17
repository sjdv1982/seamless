import inspect
from re import I
import weakref
from copy import deepcopy

from numpy import isin
import ruamel.yaml
import subprocess
import json

yaml = ruamel.yaml.YAML(typ='safe')

from ..core.protocol.cson import cson2json
from ..core.environment import validate_conda_environment
from ..compiler import languages_cson as languages_default, compilers_cson as compilers_default

class Environment:
    _props = ["_conda", "_which"]
    def __init__(self, parent):
        if parent is None:
            self._parent = lambda: None
        else:
            self._parent = weakref.ref(parent)
        self._conda = None
        self._which = None

    def _update(self):
        from .Context import Context
        from .Transformer import Transformer
        parent = self._parent()
        if parent is None:
            return
        if isinstance(parent, Context):
            parent._translate()
        elif isinstance(parent, Transformer):
            node = parent._get_htf()
            node.pop("environment", None)
            state = self._save()
            if state is not None:
                node["environment"] = state
        else:
            raise TypeError(type(parent))

    def _save(self):
        state = {}
        for prop in self._props:
            v = getattr(self, prop)
            if v is not None:
                state[prop[1:]] = v
        if not len(state):
            state = None
        json.dumps(state)
        return state

    def _load(self, state):
        old_state = self._save()
        if state != old_state:
            for prop in self._props:
                v = state.get(prop[1:])
                if v is not None:
                    setattr(self, prop, v)
            self._update()

    def set_conda(self, conda, format):
        """Definition of the conda environment.
        
This is for the context as a whole, e.g. conda packages to support
particular programming languages.

For transformer execution, please define the conda environment 
for transformers individually (Transformer.environment)"""
        if format != "yaml":
            raise NotImplementedError(format)  # must be yaml for now
        if conda is None:
            self._conda = None
            self._update()
            return
        result = yaml.load(conda)
        if not isinstance(result, dict):
            raise TypeError("Must be dict, not {}".format(type(result)))
        result["dependencies"]        
        self._conda = conda
        self._update()

    def get_conda(self, format):
        """Current definition of the conda environment
        
This is for the context as a whole, e.g. conda packages to support
particular programming languages.

For transformer execution, please define the conda environment 
for transformers individually (Transformer.environment)"""        
        if format != "yaml":
            raise NotImplementedError(format)  # must be yaml for now
        return self._conda

    def set_which(self, which, format):
        """List of binaries that must be available in the command line path, using "which" """
        if format != "plain":
            raise NotImplementedError(format)  # must be plain Python for now
        if which is None:
            self._which = None
            self._update()
            return
        if not isinstance(which, list):
            raise TypeError("Must be list, not {}".format(type(which)))
        self._which = which
        self._update()

    def get_which(self, which, format):
        """List of binaries that must be available in the command line path, using "which" """
        if format != "plain":
            raise NotImplementedError(format)  # must be plain Python for now
        return deepcopy(self._which)

    def _to_lowlevel(self):
        result = {}
        if self._which is not None:
            result["which"] = deepcopy(self._which)
        if self._conda is not None:
            conda_env = yaml.load(self._conda)
            result["conda"] = conda_env
        if not len(result):
            return None
        return result
        
    def _parse_and_validate(self):
        if self._conda is not None:
            conda_env = yaml.load(self._conda)
            result_conda = validate_conda_environment({"conda": conda_env})
            if result_conda[0] != True:
                raise ValueError(result_conda[1])
        if self._which is not None:
            for binary in self._which:
                result = subprocess.run("which " +  binary, shell=True, capture_output=True)
                if result.returncode:
                    raise ValueError("which: '{}' is not available in command line path'".format(binary))


class ContextEnvironment(Environment):
    _props = ["_conda", "_which", "_languages", "_compilers", "_ipy_templates"]
    def __init__(self, parent):
        super().__init__(parent)
        self._languages = None
        self._compilers = None
        self._ipy_templates = None

    def set_languages(self, languages, format):
        """Definition of supported languages"""
        if format not in ("cson", "plain"):
            raise NotImplementedError(format)  # must be cson for now
        if languages is None:
            self._languages = None
            self._update()
            return
        if format == "cson":
            result = cson2json(languages)
        else:
            buf = json.dumps(languages, sort_keys=True, indent=2)
            result = languages
            languages = buf
        if not isinstance(result, dict):
            raise TypeError("Must be dict, not {}".format(type(result)))
        self._languages = languages # as cson
        self._update()

    def get_languages(self, format):
        """The current definition of supported languages"""
        if format not in ("cson", "plain"):
            raise NotImplementedError(format)  # must be cson or plain
        result = self._languages
        if self._languages is None:
            result = languages_default
        if format == "cson":
            return result
        return cson2json(result)


    def set_compilers(self, compilers, format):
        """Definition of supported compilers"""
        if format not in ("cson", "plain"):
            raise NotImplementedError(format)  # must be cson or plain
        if compilers is None:
            self._compilers = None
            self._update()
            return
        if format == "cson":
            result = cson2json(compilers)
        else:
            buf = json.dumps(compilers, sort_keys=True, indent=2)
            result = compilers
            compilers = buf
        if not isinstance(result, dict):
            raise TypeError("Must be dict, not {}".format(type(result)))
        self._compilers = compilers # as cson
        self._update()

    def get_compilers(self, format):
        """The current definition of supported compilers"""
        if format not in ("cson", "plain"):
            raise NotImplementedError(format)  # must be cson or plain for now
        result = self._compilers
        if self._compilers is None:
            result = compilers_default
        if format == "cson":
            return result
        return cson2json(result)

    def find_language(self, language):
        from ..compiler import find_language
        languages = self.get_languages("plain")
        return find_language(language, languages)

    def set_ipy_template(self, language:str, template_code, parameters=None):
        """Sets an IPython template for a foreign programming language
A transformer written in that language will have the template code
applied to its .code attribute,
    and for the rest is treated as if written in IPython

The template code has similar requirements as a Python transformer:
- a Python function that takes two arguments, "code" and "parameters".
    "code" is the foreign language code. 
    "parameters" is what is supplied here.
    It must return the IPython code as a string 

- or: a string with the source code of such a Python function

- or: a code block that defines the IPython code in a variable "result"        

parameters: optional
A JSON-serializable object that will be passed to the template code
"""
        if not isinstance(language, str):
            raise TypeError(language)

        if callable(template_code):
            template_code = inspect.getsource(template_code)
            if template_code is None:
                raise ValueError("Cannot obtain source code for template_code")
            if not isinstance(template_code, str):
                raise TypeError(type(template_code))            
        if parameters is not None:
            if not isinstance(parameters, dict):
                raise TypeError(type(parameters))
        if self._ipy_templates is None:
            self._ipy_templates = {}
        tmpl = {
            "code": template_code
        }
        if parameters is not None:
            try:
                json.dumps(parameters)
            except Exception:
                raise ValueError("Parameters must be JSON-serializable") from None
            tmpl["parameters"] = deepcopy(parameters)
        self._ipy_templates[language] = tmpl
        self._update()

    def set_ipy_template_parameters(self, language, parameters) -> None:
        """Sets the IPython template parameters for a programming language
See set_ipy_template for documentation
"""
        if self._ipy_templates is None or language not in self._ipy_templates:
            raise KeyError(language)
        tmpl = self._ipy_templates[language]
        try:
            json.dumps(parameters)
        except Exception:
            raise ValueError("Parameters must be JSON-serializable") from None
        tmpl["parameters"] = deepcopy(parameters)
        self._update()

    def get_ipy_template(self, language) -> tuple:
        """Gets the IPython template for a programming language
See set_ipy_template for documentation
    
Returns a (code, parameters) tuple"""
        if self._ipy_templates is None or language not in self._ipy_templates:
            raise KeyError(language)
        tmpl = self._ipy_templates[language]
        code = tmpl["code"]
        parameters = deepcopy(tmpl.get("parameters"))
        return code, parameters
        
    def _parse_and_validate(self):
        super()._parse_and_validate()
        languages = cson2json(self._languages)
        compilers = cson2json(self._compilers)
        return {
            "languages": languages,
            "compilers": compilers
        }

