#!/usr/bin/env python3
"""A magic markdown converter, to generate html for my website

Usage:
    mdconvert <file>
    mdconvert [options] <indir> <outdir>

Options:
    -h --help               Show this screen

"""

from markdown import Markdown
from markdown.preprocessors import Preprocessor
from markdown.treeprocessors import Treeprocessor
from markdown.extensions import Extension
from markdown.util import etree
import requests, base64
import logging, os, sys, shutil, mimetypes
import feedgenerator, datetime
from urllib.parse import urljoin

def include_file(path):
    """Jinja function to read file from disk"""
    return open(path).read()

def include_image(path):
    """Jinja function to read image as base64 from disk"""
    b64 = base64.b64encode( open(path, 'rb').read() )
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

    def get_image(self, url):
        try:
            r = requests.get(url)
            if r.status_code != 200:
                logging.warning('Unable to get <img> from %s' % url )
                return None, None
            return r.content, r.headers.get('content-type')
        except requests.models.MissingSchema:
            if self.local_path:
                try:
                    path = os.path.join(self.local_path, url)
                    content = open(path, "rb").read()
                except Exception as ex:
                    logging.warning('Unable to get local <img> %s: %s' 
                            % (path, ex))
                    return None, None

                mimetype = mimetypes.guess_type(url)[0]
                if not mimetype:
                    logging.warning("Can't determine mimetype for image %s, skipping'" % url)
                    return None, None
            else:
                logging.warning('Cant find local <img> %s' % url)
                return None, None
        except Exception as ex:
            logging.warning('Unable to get <img> %s: %s' % (url, ex))
            return None, None
        return content, mimetype

    def run(self, root):
        if hasattr(self.markdown, 'Meta') and 'title' in self.markdown.Meta:
            self.markdown.ArticleTitle = self.markdown.Meta['title'][0]

        h1 = root.find('h1')
        if h1 == None:
            if self.markdown.ArticleTitle:
                pass
            else:
                logging.warning('This article has no title')
        else:
            if root[0] != h1:
                logging.warning('Disregarding late h1 title (%s)' % h1.text)
            else:
                if self.markdown.ArticleTitle:
                    logging.warning('Markdown text has two titles (%s)' % h1.text)
                self.markdown.ArticleTitle = h1.text

        self.markdown.ArticlePreamble = ''
        # Article metadata noarticle: disables the preamble paragraph
        nopreamble = hasattr(self.markdown, 'Meta') and 'noarticle' in self.markdown.Meta
        p = root.find('p')
        if p != None and not nopreamble:
            self.markdown.ArticlePreamble = etree.tostring(p, method='text', encoding='unicode')
            p.attrib['class'] = p.attrib.get('class', '') + ' article_preamble'

        imgs = root.findall('.//img')
        for img in imgs:
            src = img.attrib['src']
            if not src or src.startswith('data:'):
                continue

            content, mimetype = self.get_image(src)
            if not content:
                continue

            b64 = base64.b64encode(content)
            img.attrib['src'] = 'data:%s;base64,%s' % (mimetype, b64.decode('ascii'))

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
    Reads Markdown input from a file and returns html
    """
    with open(args['<file>']) as f:
        html,metadata = conv_markdown( f.read().decode(encoding), local_path=os.path.dirname(args['<file>']) )
        template = env.get_template('article.html')
        output = template.render(html=html, metadata=metadata, bare=True)
    return output

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

def write_rss(url, articles, out_path):
    """
    Write an RSS file from a list of articles
    """
    rss = feedgenerator.Rss201rev2Feed(
        title="raf's random writings",
        link=url,
        description='Random ramblings by a computer engineer',
        language="en")

    for art in articles:
        rss.add_item(
                    title=art['title'],
                    description=art['description'],
                    link=urljoin(url, art['href'])
                )

    with open(out_path, 'w') as fp:
        rss.write(fp, 'utf8')


def copy_static(dst):
    """Copy static/* to target folder"""
    staticfiles = [ os.path.join('static', path) for path in os.listdir('static')]
    for staticfile in staticfiles:
        if not staticfile.startswith('.'):
            shutil.copy(staticfile, dst)

def generate_html(savepath, tempname, **kw):
    """Write article HTML"""
    template = env.get_template(tempname)
    output = template.render(**kw)
    with open(savepath, 'w') as fp:
        fp.write(output)

if __name__ == '__main__':
    from docopt import docopt
    args = docopt(__doc__, version="raf's markdown converter")

    from jinja2 import Environment, FileSystemLoader
    env=Environment(loader=FileSystemLoader('templates'))
    env.globals['include_file'] = include_file
    env.globals['include_image'] = include_image

    if args['<file>']:
        print(convert_single_file(args['<file>']))
        sys.exit(0)

    # from here on, we are generating a folder
    if os.path.exists(args['<outdir>']):
        logging.warning('Output path already exists')

    try:
        os.mkdir(args['<outdir>'])
    except:
        pass

    copy_static(args['<outdir>'])

    paths = [ os.path.join(args['<indir>'], path) for path in os.listdir(args['<indir>']) if is_valid_file(path, ('', '.png'))]
    paths.sort(reverse=True)

    articles = []
    for idx, path in enumerate(paths):
        if not os.path.isfile(path):
            continue

        ext = os.path.splitext(path)[-1].lower()
        if ext:
            shutil.copy(path, args['<outdir>'])
            continue

        # Read markdown files
        a_in = open(path)
        html,metadata = conv_markdown( a_in.read(),
                                local_path=args['<indir>'] )

        data = {'html':html, 'metadata':metadata, 'basename':os.path.basename(path)}
        # Write html article
        htmlpath = os.path.join( args['<outdir>'], os.path.basename(path)+'.html')
        generate_html(htmlpath, 'article.html', **data)

        # Write print friendly version as name.print.html
        data['bare'] = True
        printpath = os.path.join( args['<outdir>'], os.path.basename(path)+'.print.html')
        generate_html(printpath, 'article.html', **data)

        if 'hidden' in metadata or 'noarticle' in metadata:
            continue

        # Write the index page
        href = os.path.basename(path) + '.html'
        articles.append({
                    'title': metadata['title'],
                    'description': metadata['description'],
                    'content': html,
                    'href': href,
                    'metadata': metadata
                    })

    # write index.html
    indexpath = os.path.join(args['<outdir>'], 'index.html')
    generate_html(indexpath, 'article_list.html', articles=articles, rss=True)

    write_rss('http://ruiabreu.org', articles, 
            os.path.join(args['<outdir>'], 'rss.xml') )

