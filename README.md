
Yet another static website generator written in Python, everybody has
one and so do I.

## Usage

This should be enough

    mdconvert sourcepath/ out/

For each file in sourcepath/ the  out/ path holds

- one HTML file
- one embedded HTML (base64 images and less javascript)

Additionally we generate an index page and RSS feed.

Files without extension are treated as markdown articles, all other are copied
to the target dir.

## Markdown semantics

Input files are markdown formatted with a couple of extensions

- Metadata is supported to store the title
- A single lone line at the top will be treated as the article title
  (vim-pad compatibility)


