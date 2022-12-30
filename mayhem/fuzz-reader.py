#! /usr/bin/python3

import atheris
import sys
import io

with atheris.instrument_imports():
    from reader import make_reader, InvalidFeedURLError

def fuzz_singleInput(input_bytes):
    fdp = atheris.FuzzedDataProvider(input_bytes)
    data_string = fdp.ConsumeUnicodeNoSurrogates(sys.maxsize)

    try:
        feed_url = data_string

        reader = make_reader("db.sqlite")

        # reader.add_feed(feed_url, exist_ok=True)
        # reader.update_feeds()
        feed = reader.get_feed(feed_url)
    except InvalidFeedURLError:
        pass

def main():
    atheris.Setup(sys.argv, fuzz_singleInput)
    atheris.Fuzz()

if __name__ == "__main__":
    main()