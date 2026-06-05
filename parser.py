import re
import yaml
import sys

class OwomdError(Exception):
    pass

def parse_metadata(text):
    begin_marker = "$HEADER_BEGIN"
    end_marker = "$HEADER_END"
    if begin_marker in text:
        start_idx = text.find(begin_marker)
        end_idx = text.find(end_marker, start_idx + len(begin_marker))
        if end_idx == -1:
            raise OwomdError("Header started with $HEADER_BEGIN but no $HEADER_END found.")
        header_content = text[start_idx + len(begin_marker):end_idx].strip()
        try:
            metadata = yaml.safe_load(header_content)
        except yaml.YAMLError as e:
            raise OwomdError(f"Malformed header, is not valid yaml: {e}")
        remaining_text = text[:start_idx] + text[end_idx + len(end_marker):]
        if remaining_text.startswith('\n'):
            remaining_text = remaining_text[1:]
        return metadata, remaining_text
    return {}, text

def resolve_escapes(text):
    # Process escapes :3c
    res = []
    i = 0
    while i < len(text):
        if text[i] == '\\':
            if i + 1 >= len(text):
                res.append('\\')
                break
            nxt = text[i+1]
            if nxt == 'u':
                if i + 2 < len(text) and text[i+2] == '{':
                    # \u{n+}
                    end = text.find('}', i + 3)
                    if end != -1:
                        hex_str = text[i+3:end]
                        try:
                            val = int(hex_str, 16)
                            if val > 0x10FFFF:
                                raise OwomdError(f"Escape value too large: {hex_str}")
                            res.append(chr(val))
                            i = end + 1
                            continue
                        except ValueError:
                            pass # Fallback on invalid hex :3c
                if i + 5 <= len(text):
                    hex_str = text[i+2:i+6]
                    try:
                        val = int(hex_str, 16)
                        res.append(chr(val))
                        i += 6
                        continue
                    except ValueError:
                        pass
            elif nxt == 'x':

                if i + 3 <= len(text):
                    hex_str = text[i+2:i+4]
                    try:
                        val = int(hex_str, 16)
                        res.append(chr(val))
                        i += 4
                        continue
                    except ValueError:
                        pass
            # Normal escape :3c
            res.append(nxt)
            i += 2
        else:
            res.append(text[i])
            i += 1
    out = "".join(res)
    if '\x00' in out:
        raise OwomdError("Null byte found in input.")
    return out

def process_document(text, placeholder_data):
    if '\x00' in text:
        raise OwomdError("Null byte found in input.")

    metadata, content = parse_metadata(text)
    
    # Expanded parser hook :3c
    return content
