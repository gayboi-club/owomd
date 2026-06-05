import re
import sys
import yaml

class OwomdError(Exception):
    pass

# AST Nodes
class Document:
    def __init__(self, blocks): self.blocks = blocks

class HeaderNode:
    def __init__(self, level, inline_nodes):
        self.level = level
        self.inline_nodes = inline_nodes

class CodeBlockNode:
    def __init__(self, lang, templating, lines):
        self.lang = lang
        self.templating = templating
        self.lines = lines

class QuoteNode:
    def __init__(self, blocks):
        self.blocks = blocks

class ListNode:
    def __init__(self, ordered, items):
        self.ordered = ordered
        self.items = items # :3c

class IteratorNode:
    def __init__(self, path, var, blocks, line_num):
        self.path = path
        self.var = var
        self.blocks = blocks
        self.line_num = line_num

class ParagraphNode:
    def __init__(self, inline_nodes):
        self.inline_nodes = inline_nodes

# Inline Nodes
class TextNode:
    def __init__(self, text): self.text = text
class EmphasisNode:
    def __init__(self, style, inline_nodes):
        self.style = style # 'bold', 'italic', 'underline', 'code'
        self.inline_nodes = inline_nodes
class LinkNode:
    def __init__(self, text_nodes, url):
        self.text_nodes = text_nodes
        self.url = url
class ImageNode:
    def __init__(self, alt, url):
        self.alt = alt
        self.url = url
class PlaceholderNode:
    def __init__(self, path, line_num):
        self.path = path
        self.line_num = line_num

def extract_metadata(text):
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

def parse_inline(text, line_num):
    nodes = []
    i = 0
    current_text = ""
    
    def flush_text():
        nonlocal current_text
        if current_text:
            nodes.append(TextNode(current_text))
            current_text = ""

    while i < len(text):
        if text[i] == '\\':
            if i + 1 >= len(text):
                current_text += '\\'
                i += 1
                break
            nxt = text[i+1]
            if nxt == 'u':
                if i + 2 < len(text) and text[i+2] == '{':
                    end = text.find('}', i + 3)
                    if end != -1:
                        hex_str = text[i+3:end]
                        try:
                            val = int(hex_str, 16)
                            if val > 0x10FFFF:
                                raise OwomdError(f"Escape value too large: {hex_str}")
                            current_text += chr(val)
                            i = end + 1
                            continue
                        except ValueError:
                            pass
                if i + 5 < len(text):
                    hex_str = text[i+2:i+6]
                    try:
                        val = int(hex_str, 16)
                        current_text += chr(val)
                        i += 6
                        continue
                    except ValueError:
                        pass
            elif nxt == 'x':
                if i + 3 < len(text):
                    hex_str = text[i+2:i+4]
                    try:
                        val = int(hex_str, 16)
                        current_text += chr(val)
                        i += 4
                        continue
                    except ValueError:
                        pass
            # Generic escape :3c
            current_text += nxt
            i += 2
            continue
            
        elif text.startswith('${', i):
            end = text.find('}', i + 2)
            if end != -1:
                flush_text()
                path = text[i+2:end].strip()
                nodes.append(PlaceholderNode(path, line_num))
                i = end + 1
                continue
                

        current_text += text[i]
        i += 1
        
    flush_text()
    return nodes
