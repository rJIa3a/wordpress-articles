"""Offset-preserving local sentence context, independent of gold annotations."""
import re

def sentence_span(text,start,end):
    if not 0<=start<end<=len(text):raise ValueError('Invalid anchor span')
    boundaries=[m.end() for m in re.finditer(r'[.!?](?:[»”\"])?\s+(?=[А-ЯЁA-Z])|\n+',text)]
    left=max([0]+[b for b in boundaries if b<=start])
    right=min([len(text)]+[b for b in boundaries if b>=end])
    return left,right

def sentence_features(text,start,end):
    left,right=sentence_span(text,start,end);fragment=text[left:right]
    return [float(start-left)/max(1,right-left),len(fragment)/max(1,len(text)),
            int(text[left:start].count('(')>text[left:start].count(')')),
            len(re.findall(r'\b[А-ЯЁ][а-яё]+',fragment)),0]
