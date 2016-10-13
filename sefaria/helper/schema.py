# -*- coding: utf-8 -*-

from sefaria.model import *

"""
Experimental
These utilities have been used a few times, but are still rough.

To get the existing schema nodes to pass into these functions, easiest is likely:
Ref("...").index_node


Todo:
    Clean system from old refs:
        links to commentary
        transx reqs
        elastic search
        varnish
"""


def insert_last_child(new_node, parent_node):
    return attach_branch(new_node, parent_node, len(parent_node.children))


def insert_first_child(new_node, parent_node):
    return attach_branch(new_node, parent_node, 0)


def attach_branch(new_node, parent_node, place=0):
    """
    :param new_node: A schema node tree to attach
    :param parent_node: The parent to attach it to
    :param place: The index of the child before which to insert, so place=0 inserts at the front of the list, and place=len(parent_node.children) inserts at the end
    :return:
    """
    assert isinstance(new_node, SchemaNode)
    assert isinstance(parent_node, SchemaNode)
    assert place <= len(parent_node.children)

    index = parent_node.index

    # Add node to versions & commentary versions
    vs = [v for v in index.versionSet()]
    vsc = [v for v in library.get_commentary_versions_on_book(index.title)]
    for v in vs + vsc:
        pc = v.content_node(parent_node)
        pc[new_node.key] = new_node.create_skeleton()
        v.save(override_dependencies=True)

    # Update Index schema and save
    parent_node.children.insert(place, new_node)
    new_node.parent = parent_node

    index.save(override_dependencies=True)
    library.rebuild()
    refresh_version_state(index.title)


def remove_branch(node):
    """
    This will delete any text in `node`
    :param node: SchemaNode to remove
    :return:
    """
    assert isinstance(node, SchemaNode)
    parent = node.parent
    assert parent
    index = node.index

    node.ref().linkset().delete()
    # todo: commentary linkset

    vs = [v for v in index.versionSet()]
    vsc = [v for v in library.get_commentary_versions_on_book(index.title)]
    for v in vs + vsc:
        assert isinstance(v, Version)
        pc = v.content_node(parent)
        del pc[node.key]
        v.save(override_dependencies=True)

    parent.children = [n for n in parent.children if n.key != node.key]

    index.save(override_dependencies=True)
    library.rebuild()
    refresh_version_state(index.title)


def reorder_children(parent_node, new_order):
    """
    :param parent_node:
    :param new_order: List of child keys, in their new order
    :return:
    """
    # With this one, we can get away with just an Index change
    assert isinstance(parent_node, SchemaNode)
    child_dict = {n.key: n for n in parent_node.children}
    assert set(child_dict.keys()) == set(new_order)
    parent_node.children = [child_dict[k] for k in new_order]
    parent_node.index.save()


def merge_default_into_parent(parent_node):
    """
    In a case where a parent has only one child - a default child - this merges the two together into one Jagged Array node.

    Example Usage:
    >>> r = Ref('Mei HaShiloach, Volume II, Prophets, Judges')
    >>> merge_default_into_parent(r.index_node)

    :param parent_node:
    :return:
    """
    assert isinstance(parent_node, SchemaNode)
    assert len(parent_node.children) == 1
    assert parent_node.has_default_child()
    default_node = parent_node.get_default_child()
    #assumption: there's a grandparent.  todo: handle the case where the parent is the root node of the schema
    is_root = True
    if parent_node.parent:
        is_root = False
        grandparent_node = parent_node.parent
    index = parent_node.index

    # Repair all versions
    vs = [v for v in index.versionSet()]
    vsc = [v for v in library.get_commentary_versions_on_book(index.title)]
    for v in vs + vsc:
        assert isinstance(v, Version)
        if is_root:
            v.chapter = v.chapter["default"]
        else:
            grandparent_version_dict = v.sub_content(grandparent_node.version_address())
            grandparent_version_dict[parent_node.key] = grandparent_version_dict[parent_node.key]["default"]
        v.save(override_dependencies=True)

    # Rebuild Index
    new_node = JaggedArrayNode()
    new_node.key = parent_node.key
    new_node.title_group = parent_node.title_group
    new_node.sectionNames = default_node.sectionNames
    new_node.addressTypes = default_node.addressTypes
    new_node.depth = default_node.depth
    if is_root:
        index.nodes = new_node
    else:
        grandparent_node.children = [c if c.key != parent_node.key else new_node for c in grandparent_node.children]

    # Save index and rebuild library
    index.save(override_dependencies=True)
    library.rebuild()
    refresh_version_state(index.title)


def convert_simple_index_to_complex(index):
    """
    The target complex text will have a 'default' node.
    All refs to this text should remain good.
    :param index:
    :return:
    """
    from sefaria.model.schema import TitleGroup

    assert isinstance(index, Index)

    ja_node = index.nodes
    assert isinstance(ja_node, JaggedArrayNode)

    # Repair all version
    vs = [v for v in index.versionSet()]
    vsc = [v for v in library.get_commentary_versions_on_book(index.title)]
    for v in vs + vsc:
        assert isinstance(v, Version)
        v.chapter = {"default": v.chapter}
        v.save(override_dependencies=True)

    # Build new schema
    new_parent = SchemaNode()
    new_parent.title_group = ja_node.title_group
    new_parent.key = ja_node.key
    ja_node.title_group = TitleGroup()
    ja_node.key = "default"
    ja_node.default = True

    # attach to index record
    new_parent.append(ja_node)
    index.nodes = new_parent

    index.save(override_dependencies=True)
    library.rebuild()
    refresh_version_state(index.title)


def change_parent(node, new_parent, place=0):
    """
    :param node:
    :param new_parent:
    :param place: The index of the child before which to insert, so place=0 inserts at the front of the list, and place=len(parent_node.children) inserts at the end
    :return:
    """
    assert isinstance(node, SchemaNode)
    assert isinstance(new_parent, SchemaNode)
    assert place <= len(new_parent.children)
    old_parent = node.parent
    index = new_parent.index

    old_normal_form = node.ref().normal()
    linkset = [l for l in node.ref().linkset()]

    vs = [v for v in index.versionSet()]
    vsc = [v for v in library.get_commentary_versions_on_book(index.title)]
    for v in vs + vsc:
        assert isinstance(v, Version)
        old_parent_content = v.content_node(old_parent)
        content = old_parent_content.pop(node.key)
        new_parent_content = v.content_node(new_parent)
        new_parent_content[node.key] = content
        v.save(override_dependencies=True)

    old_parent.children = [n for n in old_parent.children if n.key != node.key]
    new_parent.children.insert(place, node)
    node.parent = new_parent
    new_normal_form = node.ref().normal()

    index.save(override_dependencies=True)
    library.rebuild()

    for link in linkset:
        link.refs = [ref.replace(old_normal_form, new_normal_form) for ref in link.refs]
        link.save()
    # todo: commentary linkset

    refresh_version_state(index.title)


def refresh_version_state(base_title):
    """
    ** VersionState is *not* altered on Index save.  It is only created on Index creation.
    ^ It now seems that VersionState is referenced on Index save

    VersionState is *not* automatically updated on Version save.
    The VersionState update on version save happens in texts_api().
    VersionState.refresh() assumes the structure of content has not changed.
    To regenerate VersionState, we save the flags, delete the old one, and regenerate a new one.
    """
    vtitles = library.get_commentary_version_titles_on_book(base_title) + [base_title]
    for title in vtitles:
        vs = VersionState(title)
        flags = vs.flags
        vs.delete()
        VersionState(title, {"flags": flags})


def change_node_title(snode, old_title, lang, new_title):
    """
    Changes the title of snode specified by old_title and lang, to new_title.
    If the title changing is the primary english title, cascades to all of the impacted objects
    :param snode:
    :param old_title:
    :param lang:
    :param new_title:
    :return:
    """
    pass


def replaceBadNodeTitles(title, bad_char, good_char, lang):
    '''
    This recurses through the serialized tree changing replacing the previous title of each node to its title with the bad_char replaced by good_char. 
    '''
    def recurse(node):
        if 'nodes' in node:
            for each_one in node['nodes']:
                recurse(each_one)
        elif 'default' not in node:

            if 'title' in node:
                node['title'] = node['title'].replace(bad_char, good_char)
            if 'titles' in node:
                which_one = -1
                if node['titles'][0]['lang'] == lang:
                    which_one = 0
                elif len(node['titles']) > 1 and node['titles'][1]['lang'] == lang:
                    which_one = 1
                if which_one >= 0:
                    node['titles'][which_one]['text'] = node['titles'][which_one]['text'].replace(bad_char, good_char)
 
    data = library.get_index(title).nodes.serialize()
    recurse(data)
    return data


