import re
from waliki.signals import page_saved
from optparse import make_option
from django.core.management.base import BaseCommand, CommandError
from waliki.models import Page
from django.utils.translation import ugettext_lazy as _
from django.utils.text import get_text_list
try:
    from waliki.attachments.models import Attachment
except ImportError:
    Attachment = None


def clean_meta(rst_content):
    """remove moinmoin metada from the top of the file"""

    rst = rst_content.split('\n')
    for i, line in enumerate(rst):
        if line.startswith('#'):
            continue
        break
    return '\n'.join(rst[i:])


def delete_relative_links(rst_content):
    """remove links relatives. Waliki point them correctly implicitly"""

    return re.sub(r'^(\.\. .*: \.\./.*)\n$', '', rst_content, flags=re.MULTILINE)


def attachments(rst_content, slug):

    def rep(matchobj):
        for filename in matchobj.groups(1):
            try:
                a = Attachment.objects.filter(file__endswith=filename, page__slug=slug)[0]
            except IndexError:
                print('Cant find %s in %s' % (filename, slug))
                return None
        return '`%s <%s>`_' % (filename, a.get_absolute_url())

    return re.sub(r'`attachment:(.*)`_', rep, rst_content, flags=re.MULTILINE)


def directives(rst_content):
    for directive in re.findall(r':(\w+):`.*`', rst_content, flags=re.MULTILINE):
        rst_content += """

.. role:: {directive}
   :class: {directive}

""".format(directive=directive)
    return rst_content


def emojis(rst_content):
    # require
    emojis_map = {
        ':)': 'smile',
        ':-)': 'smile',
        ';)': 'wink',
        ';-)': 'wink',
        ':-?': 'smirk',
        ':?': 'smirk',
        ':(': 'confused',
        ':-(': 'confused',
        ':D': 'laughing',
        ':-D': 'laughing',
        ':-P': 'stuck_out_tongue_closed_eyes',
        ':P': 'stuck_out_tongue_closed_eyes',
        ":'(": 'cry',
        ":'-(": 'cry',
    }

    def replace_emoji(pattern):

        replacement = emojis_map.get(pattern.groups()[0], '')
        import ipdb; ipdb.set_trace()
        if replacement:
            return '|%s|' % replacement
        return ''
    result = re.sub(r'\|((?:\:|;).{1,3})\|', replace_emoji, rst_content, flags=re.MULTILINE)
    return result


class Command(BaseCommand):
    help = 'Cleanups for a moin2git import'

    option_list = (
        make_option('--limit-to',
                    dest='slug',
                    default='',
                    help="optional slug namespace"),
        make_option('--apply-filter',
                    dest='filters',
                    default='all',
                    help="comma separated list of filter functions to apply"),
        make_option('--message',
                    dest='message',
                    default=_("RestructuredText clean up"),
                    help="log message"),
    ) + BaseCommand.option_list

    def handle(self, *args, **options):
        valid_filters = ['clean_meta', 'delete_relative_links',
                         'attachments', 'directives',
                         'emojis', 'set_title']
        slug = options['slug']
        filters = options['filters']

        if filters == 'all':
            filters = valid_filters

        else:
            filters = [f.strip() for f in filters.split(',')]
            if not set(filters).issubset(valid_filters):
                valid = get_text_list(valid_filters, 'and')
                raise CommandError("At least one filter is unknown\n. Valid filters are %s" % valid)

        if slug:
            pages = Page.objects.filter(slug__startswith=slug)
        else:
            pages = Page.objects.all()

        for page in pages:
            title = None
            print('\nApplying filter/s %s to %s' % (get_text_list(filters, 'and'), page.slug))
            raw = page.raw
            if 'clean_meta' in filters:
                raw = clean_meta(raw)
            if 'delete_relative_links' in filters:
                raw = delete_relative_links(raw)
            if 'attachments' in filters:
                raw = attachments(raw, page.slug)

            if 'directives' in filters:
                raw = directives(raw)

            if 'emojis' in filters:
                raw = emojis(raw)

            if 'set_title' in filters and not page.title:
                title = page._get_part('get_document_title')

            if raw != page.raw or title:
                if title:
                    page.title = title
                if raw != page.raw:
                    page.raw = raw
                page.save()
                page_saved.send_robust(sender='moin',
                                       page=page,
                                       author=None,
                                       message=options['message'],
                                       form_extra_data={})
            else:
                print('Nothing changed. Ignoring update')
