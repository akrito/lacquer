def parse_headers(message):
    """
    Turn a Message object into a list of WSGI-style headers.
    """
    filtered_headers = ['transfer-encoding']
    headers_out = []
    for full_header in message.headers:
        if not full_header:
            # Shouldn't happen, but we'll just ignore
            continue
        if full_header[0].isspace():
            # Continuation line, add to the last header
            if not headers_out:
                raise ValueError(
                    "First header starts with a space (%r)" % full_header)
            last_header, last_value = headers_out.pop()
            value = last_value + ', ' + full_header.strip()
            headers_out.append((last_header, value))
            continue
        try:
            header, value = full_header.split(':', 1)
        except:
            raise ValueError("Invalid header: %r" % full_header)
        value = value.strip()
        if header.lower() not in filtered_headers:
            headers_out.append((header, value))
    return headers_out
