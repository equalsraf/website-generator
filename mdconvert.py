#!/usr/bin/env python
"""A magic markdown converter, to generate html for my website

Usage:
    mdconvert <file>
    mdconvert [options] <indir> <outdir>

Options:
    -h --help               Show this screen
    --dotcloud APPNAME      Generate dotcloud file

"""

from __future__ import unicode_literals, absolute_import
from markdown import Markdown
from markdown.preprocessors import Preprocessor
from markdown.treeprocessors import Treeprocessor
from markdown.extensions import Extension
from markdown.util import etree
import requests, base64
import logging, os, sys
import mimetypes
import PyRSS2Gen, datetime
import shutil
from urlparse import urljoin

def include_file(path, encoding='utf8'):
    return file(path).read().decode(encoding)

def include_image(path):
    b64 = base64.b64encode( file(path).read() )
    mimetype = mimetypes.guess_type(path)[0]
    return 'data:%s;base64,%s' % (mimetype, b64)

class ArticlePreProcessor(Preprocessor):
    """
    Handle title lines from VimPad

    If we find a lone line at the first line of the text
    store it as .ArticleTitle
    """

    def run(self, lines):
        self.markdown.ArticleTitle = ''

        first = lines[0]
        second = lines[1]

        # The first line is the title if the second line is empty
        # and it holds no ':' chars
        if first and not second and not ':' in first:
            self.markdown.ArticleTitle = first.lstrip('# ')
            return lines[2:]

        return lines

class ArticleTreeProcessor(Treeprocessor):
    """
    A markdown extension to help generate my articles

    1. Extract the first paragraph of the document and
       place it at .ArticlePreamble
    2. Replace external image with embeded images
    3. If an h1 title found store it as .ArticleTitle
    """
    def __init__(self, md, local_path=None):
        Treeprocessor.__init__(self, md)
        self.local_path = local_path

    def run(self, root):
        if hasattr(self.markdown, 'Meta') and 'title' in self.markdown.Meta:
            self.markdown.ArticleTitle = self.markdown.Meta['title'][0]

        h1 = root.find('h1')
        if h1 == None:
            if self.markdown.ArticleTitle:
                h1 = etree.Element('h1')
                h1.text = self.markdown.ArticleTitle
                root.insert(0, h1)
            else:
                logging.warning('This article has no title')
        else:
            if root[0] != h1:
                logging.warning('Disregarding late h1 title (%s)' % h1.text)
                h1 = etree.Element('h1')
                h1.text = self.markdown.ArticleTitle
                root.insert(0, h1)
            else:
                if self.markdown.ArticleTitle:
                    logging.warning('Markdown text has two titles (%s)' % h1.text)
                self.markdown.ArticleTitle = h1.text

        self.markdown.ArticlePreamble = ''
        p = root.find('p')
        if p != None:
            self.markdown.ArticlePreamble = p.text
            p.attrib['class'] = p.attrib.get('class', '') + ' article_preamble'

        imgs = root.findall('.//img')
        for img in imgs:
            src = img.attrib['src']
            if not src or src.startswith('data:'):
                continue

            try:
                r = requests.get(src)
                if r.status_code != 200:
                    logging.warning('Unable to get <img> from %s' % src )
                    continue
                content = r.content
                mimetype = r.headers.get('content-type')
            except requests.models.MissingSchema:
                if self.local_path:
                    try:
                        content = file(os.path.join(self.local_path, src)).read()
                    except:
                        logging.warning('Unable to get local <img> %s' % src)
                        continue

                    mimetype = mimetypes.guess_type(src)[0]
                    if not mimetype:
                        logging.warning("Can't determine mimetype for image %s, skipping'" % src)
                        continue
                else:
                    logging.warning('Found local <img> %s' % src)
                    continue
            except:
                logging.warning('Unable to get <img> %s' % src)
                continue

            b64 = base64.b64encode(content)
            img.attrib['src'] = 'data:%s;base64,%s' % (mimetype, b64)

        return root

class ArticleExtension(Extension):

    def __init__(self, local_path=None):
        Extension.__init__(self)
        self.local_path = local_path

    def extendMarkdown(self, md, md_globals):
        md.preprocessors.add('article', ArticlePreProcessor(md), '_begin')
        md.treeprocessors.add('article', ArticleTreeProcessor(md, local_path=self.local_path), '_end' )

def conv_markdown(content, local_path=None):
    """
    Our magick markdown converter

    1. Read first line in file
    2. If it has text and is not metadata, use it
       as title (vim-pad)
    3. Use markdown-meta['title']
    4. Use parsed h1 title
    """

    md = Markdown( extensions=['meta', 'codehilite', 'fenced_code', ArticleExtension(local_path=local_path)])
    content = md.convert(content)
    metadata = md.Meta
    metadata['description'] = md.ArticlePreamble
    metadata['title'] = md.ArticleTitle

    return (content, metadata)


def convert_single_file(path, encoding='utf8'):
    """
    Reads Markdown input from a file and returns parsed html
    """
    with file(args['<file>']) as f:
        html = conv_markdown( f.read().decode(encoding), local_path=os.path.dirname(args['<file>']) )[0]
    return html

def is_valid_file(path, exts=('',)):
    """
    Returns False for:

    * hidden files(starting with '.')
    * files with no extension
    """
    if path.startswith('.') or path.endswith('~'):
        return False

    ext = os.path.splitext(path)[-1].lower()
    if ext in exts:
        return True

    return False

def write_rss(articles, out_path):
    """
    Write an RSS file from a list of articles
    """
    items = []
    for art in articles:
        item = PyRSS2Gen.RSSItem(
                    title=art['title'],
                    description=art['description'],
                    link=urljoin(url_prefix, art['href'])
                    )
        items.append(item)

    rss = PyRSS2Gen.RSS2(title="raf's random writings",
                        description='Random ramblings by a computer engineer',
                        link=url_prefix,
                        lastBuildDate = datetime.datetime.now(),
                        items=items)
    rss.write_xml(open(out_path, 'w'))


if __name__ == '__main__':
    from docopt import docopt
    args = docopt(__doc__, version="raf's markdown converter")

    if args['<file>']:
        print(convert_single_file(args['<file>']))
        sys.exit(0)

    # from here on, we are generating a folder
    from jinja2 import Environment, FileSystemLoader
    env=Environment(loader=FileSystemLoader('templates'))
    env.globals['include_file'] = include_file
    env.globals['include_image'] = include_image

    if os.path.exists(args['<outdir>']):
        logging.warning('Output path already exists')

    try:
        os.mkdir(args['<outdir>'])
    except:
        pass

    paths = [ os.path.join(args['<indir>'], path.decode('utf8')) for path in os.listdir(args['<indir>']) if is_valid_file(path.decode('utf8'), ('', '.png'))]
    paths.sort(reverse=True)

    articles = []
    for idx, path in enumerate(paths):
        if not os.path.isfile(path):
            continue

        ext = os.path.splitext(path)[-1].lower()
        if ext:
            shutil.copy(path, args['<outdir>'])
            continue

        # html files
        a_in = file(path)
        a_out = file(os.path.join( args['<outdir>'], os.path.basename(path)+'.html'), 'w')
        html,metadata = conv_markdown( a_in.read().decode('utf-8'),
                                local_path=args['<indir>'] )

        template = env.get_template('article.html')
        output = template.render(html=html, metadata=metadata, basename=os.path.basename(path))
        a_out.write(output.encode('utf-8'))

        if 'hidden' in metadata:
            continue

        href = os.path.basename(path) + '.html'
        articles.append({
                    'title': metadata['title'],
                    'description': metadata['description'],
                    'content': html,
                    'href': href,
                    })

    url_prefix = 'http://ruiabreu.org/'

    # write index.html
    template = env.get_template('article_list.html')
    output = template.render(articles=articles, rss=True)
    file(os.path.join(args['<outdir>'], 'index.html'), 'w').write(output.encode('utf-8'))

    write_rss(articles, os.path.join(args['<outdir>'], 'rss.xml') )

    # Generate dotloud file
    if args['--dotcloud']:
        import yaml
        with file(os.path.join(args['<outdir>'], 'dotcloud.yml'), 'w') as f:
            data = { 'www' : {'type': 'static'}}
            yaml.safe_dump(data, f, default_flow_style=False)



