from django.shortcuts import render
import markdown
from wiki.models import Article


# Create your views here.

def home(request):
    return render(request, 'base.html')


def editor(request):
    return render(request, 'editor.html')


def error(request):
    return render(request, 'error.html')


def create(request):
    return render(request, 'editor.html')


def md_show(request, title):
    flag = False
    try:
        Article.objects.get(id=title)
    except Article.DoesNotExist:
        flag = True
    except Article.MultipleObjectsReturned:
        flag = True
    if flag:
        return render(request, 'editor.html')
    # 将markdown语法渲染成html样式
    article = Article.objects.get(id=title)
    article.content = markdown.markdown(article.content,
                                        extensions=[
                                            'markdown.extensions.extra',  # 用于标题、表格、引用这些基本转换
                                            'markdown.extensions.codehilite',  # 用于语法高亮
                                            'markdown.extensions.toc',  # 用于生成目录
                                            'markdown.extensions.abbr',
                                            'markdown.extensions.attr_list',
                                            'markdown.extensions.def_list',
                                            'markdown.extensions.fenced_code',
                                            'markdown.extensions.footnotes',
                                            'markdown.extensions.tables',
                                            'markdown.extensions.admonition',
                                            'markdown.extensions.meta',
                                            'markdown.extensions.nl2br',
                                            'markdown.extensions.sane_lists',
                                            'markdown.extensions.smarty',
                                            'markdown.extensions.wikilinks',
                                        ])
    context = {'article': article}
    return render(request, 'example.html', context)


def md_editor(request):
    method = request.GET.get('action', )
    if method == 'editor':
        method = '编辑页面'
    if method == 'create':
        method = '创建页面'
    if method != '编辑页面' or method != '创建页面':
        return render(request, 'error.html')
    context = {
        'method': method
    }
    return render(request, 'editor.html', context)




