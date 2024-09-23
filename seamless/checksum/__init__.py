"""Functions and classes related to Seamless checksums and buffers"""

from .expression import Expression

empty_dict_checksum = "d0a1b2af1705c1b8495b00145082ef7470384e62ac1c4d9b9cdbbe0476c28f8c"
empty_list_checksum = "7b41ad4a50b29158e075c6463133761266adb475130b8e886f2f5649070031cf"


__all__ = ["Expression", "empty_dict_checksum", "empty_list_checksum"]
