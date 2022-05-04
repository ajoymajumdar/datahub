import re
from abc import ABC, abstractmethod
from typing import IO, Any, Dict, List, Optional, Pattern, cast

from pydantic import BaseModel


class ConfigModel(BaseModel):
    class Config:
        extra = "forbid"


class DynamicTypedConfig(ConfigModel):
    type: str
    # This config type is declared Optional[Any] here. The eventual parser for the
    # specified type is responsible for further validation.
    config: Optional[Any]


class MetaError(Exception):
    """A base class for all meta exceptions"""


class PipelineExecutionError(MetaError):
    """An error occurred when executing the pipeline"""


class OperationalError(PipelineExecutionError):
    """An error occurred because of client-provided metadata"""

    message: str
    info: dict

    def __init__(self, message: str, info: dict = None):
        self.message = message
        if info:
            self.info = info
        else:
            self.info = {}


class ConfigurationError(MetaError):
    """A configuration error has happened"""


class SensitiveError(Exception):
    """Wraps an exception that should not be logged with variable information."""

    @classmethod
    def get_sensitive_cause(cls, exc: Exception) -> Optional[Exception]:
        """
        Returns the underlying exception if the exception is sensitive, and None otherwise.
        """

        e: Optional[Exception] = exc
        while e:
            # This cast converts BaseException to Exception.
            inner = cast(Optional[Exception], e.__cause__)

            if isinstance(e, cls):
                return inner
            e = inner
        return None


class ConfigurationMechanism(ABC):
    @abstractmethod
    def load_config(self, config_fp: IO) -> dict:
        pass


class OauthConfiguration(ConfigModel):
    provider: Optional[str]
    client_id: Optional[str]
    scopes: Optional[List[str]]
    use_certificate: Optional[str]
    client_secret: Optional[str]
    authority_url: Optional[str]
    encoded_oauth_public_key: Optional[str]
    encoded_oauth_private_key: Optional[str]


class AllowDenyPattern(ConfigModel):
    """A class to store allow deny regexes"""

    allow: List[str] = [".*"]
    deny: List[str] = []
    ignoreCase: Optional[
        bool
    ] = True  # Name comparisons should default to ignoring case
    alphabet: str = "[A-Za-z0-9 _.-]"

    @property
    def alphabet_pattern(self) -> Pattern:
        return re.compile(f"^{self.alphabet}+$")

    @property
    def regex_flags(self) -> int:
        if self.ignoreCase:
            return re.IGNORECASE
        else:
            return 0

    @classmethod
    def allow_all(cls) -> "AllowDenyPattern":
        return AllowDenyPattern()

    def allowed(self, string: str) -> bool:
        for deny_pattern in self.deny:
            if re.match(deny_pattern, string, self.regex_flags):
                return False

        for allow_pattern in self.allow:
            if re.match(allow_pattern, string, self.regex_flags):
                return True

        return False

    def is_fully_specified_allow_list(self) -> bool:
        """
        If the allow patterns are literals and not full regexes, then it is considered
        fully specified. This is useful if you want to convert a 'list + filter'
        pattern into a 'search for the ones that are allowed' pattern, which can be
        much more efficient in some cases.
        """
        for allow_pattern in self.allow:
            if not self.alphabet_pattern.match(allow_pattern):
                return False
        return True

    def get_allowed_list(self) -> List[str]:
        """Return the list of allowed strings as a list, after taking into account deny patterns, if possible"""
        assert self.is_fully_specified_allow_list()
        return [a for a in self.allow if self.allowed(a)]


class KeyValuePattern(ConfigModel):
    """A class to store allow deny regexes"""

    rules: Dict[str, List[str]] = {".*": []}
    alphabet: str = "[A-Za-z0-9 _.-]"

    @property
    def alphabet_pattern(self) -> Pattern:
        return re.compile(f"^{self.alphabet}+$")

    @classmethod
    def all(cls) -> "KeyValuePattern":
        return KeyValuePattern()

    def value(self, string: str) -> List[str]:
        for key in self.rules.keys():
            if re.match(key, string):
                return self.rules[key]
        return []

    def matched(self, string: str) -> bool:
        for key in self.rules.keys():
            if re.match(key, string):
                return True
        return False

    def is_fully_specified_key(self) -> bool:
        """
        If the allow patterns are literals and not full regexes, then it is considered
        fully specified. This is useful if you want to convert a 'list + filter'
        pattern into a 'search for the ones that are allowed' pattern, which can be
        much more efficient in some cases.
        """
        for key in self.rules.keys():
            if not self.alphabet_pattern.match(key):
                return True
        return False

    def get(self) -> Dict[str, List[str]]:
        """Return the list of allowed strings as a list, after taking into account deny patterns, if possible"""
        assert self.is_fully_specified_key()
        return self.rules


class VersionedConfig(ConfigModel):
    version: str = "1"
