"""Define three servers that can perform dummy remote caching for transformer results
The first one returns first, but returns None
The second one returns 42 after 3 seconds
The third one returns 43 after 5 seconds, i.e. it should be canceled
"""