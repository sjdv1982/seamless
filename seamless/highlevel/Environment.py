import weakref
from copy import deepcopy
import ruamel.yaml
import subprocess
import json

yaml = ruamel.yaml.YAML(typ='safe')

from ..core.protocol.cson import cson2json
from ..core.environment import validate_conda_environment
from ..compiler import languages_cson as languages_default, compilers_cson as compilers_default

class Environment:
    def __init__(self, parent):
        self._parent = weakref.ref(parent)
        self._languages = None
        self._compilers = None
        self._conda = None
        self._which = None

    def set_languages(self, languages, format):
        """Definition of supported languages"""
        if format not in ("cson", "plain"):
            raise NotImplementedError(format)  # must be cson for now
        if languages is None:
            self._languages = None
            self._parent()._translate()
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
        self._parent()._translate()

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
            self._parent()._translate()
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
        self._parent()._translate()

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
            self._parent()._translate()
            return
        result = yaml.load(conda)
        if not isinstance(result, dict):
            raise TypeError("Must be dict, not {}".format(type(result)))
        result["dependencies"]        
        self._conda = conda
        self._parent()._translate()

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
            self._parent()._translate()
            return
        if not isinstance(which, list):
            raise TypeError("Must be list, not {}".format(type(which)))
        self._which = which
        self._parent()._translate()

    def get_which(self, which, format):
        """List of binaries that must be available in the command line path, using "which" """
        if format != "plain":
            raise NotImplementedError(format)  # must be plain Python for now
        return deepcopy(self._which)

    def find_language(self, language):
        from ..compiler import find_language
        languages = self.get_languages("plain")
        return find_language(language, languages)

    def _parse_and_validate(self):
        if self._conda is not None:
            conda_env = yaml.load(self._conda)
            result_conda = validate_conda_environment({"conda": conda_env})
            if result_conda[0] != True:
                raise ValueError(result_conda[1])
        if self._which is not None:
            for binary in self._which:
                result = subprocess.run("which " +  binary, shell=True)
                if result.returncode:
                    raise ValueError("which: '{}' is not available in command line path'".format(binary))
        languages = cson2json(self._languages)
        compilers = cson2json(self._compilers)
        return {
            "languages": languages,
            "compilers": compilers
        }
