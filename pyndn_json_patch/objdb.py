import copy

import jsonpatch


class ObjDb:
    objs: dict[str, dict[int, any]]
    patch_lst: list

    def __init__(self):
        self.objs = {}
        self.patch_lst = []

    def resolve_json(self, name: str) -> dict[str, any]:
        obj = self.get_item(name)
        base_name, _ = self.name_sep_ver(name)
        if not obj:
            return {}
        children = obj.get('@children', {})
        if not children:
            return obj
        ret = obj.copy()
        ret['@children'] = {
            chd_id: self.resolve_json(f'{base_name}/{chd_id}/v={chd_ver}')
            for chd_id, chd_ver in children.items()
        }
        return ret

    def resolve_html(self, name: str) -> str:
        return self.json_to_html(self.resolve_json(name))

    @classmethod
    def json_to_html(cls, obj: dict[str, any]) -> str:
        prim = obj.get('@type', '')
        ent_id = obj.get('@id', '')
        ent_class = obj.get('@class', '')
        children = obj.get('@children', {})
        if not prim:
            # Failed due to no primitive name
            return ''
        else:
            ret = ''
            ret += f'<{prim}'
            ret += f' id="{ent_id}"' if ent_id else ''
            ret += f' class="{ent_class}"' if ent_class else ''
            # properties
            ret += ''.join(
                f' {k}="{cls.prop_to_html(v)}"'
                for k, v in obj.items()
                if k and k[0] != '@')
            ret += '>'
            # sub-entities
            ret += ''.join(
                cls.json_to_html(chd_val)
                for _, chd_val in children.items())
            ret += f'</{prim}>'
            return ret

    @classmethod
    def prop_to_html(cls, value: any) -> str:
        if isinstance(value, list):
            # for array
            return ','.join(cls.prop_to_html(v) for v in value)
        elif isinstance(value, dict):
            # for multi-property component
            return ' '.join(f'{k}: {cls.prop_to_html(v)};' for k, v in value.items())
        elif isinstance(value, bool):
            return 'true' if value else 'false'
        else:
            # string includes vec2, vec3 and vec4
            # Since JSON does not recognize these fields. We do a quick and dirty solution.
            return str(value)

    @staticmethod
    def name_sep_ver(name: str) -> (str, int):
        last_comp_idx = name.rfind('/')
        if last_comp_idx >= 0:
            last_comp = name[last_comp_idx + 1:]
            if last_comp.startswith('v='):
                path = name[:last_comp_idx]
                if not path:
                    path = '/'
                try:
                    ver = int(last_comp[2:])
                    return path, ver
                except ValueError:
                    return '', -1
            else:
                return name, -1
        else:
            # Invalid name. The path must start with '/'
            return '', -1

    def get_item(self, name: str) -> dict[str, any] | None:
        # Check version
        if not name:
            return None
        path, ver = self.name_sep_ver(name)
        if not path:
            return None
        obj_vers = self.objs.get(path, None)
        if not obj_vers:
            return None
        if ver < 0:
            ver = max(obj_vers.keys())
        return obj_vers.get(ver, None)

    def new_item(self, obj: dict[str, any]):
        ver = obj.get('@version', None)
        path = obj.get('@name', '')
        if not path:
            raise ValueError(f'Invalid object for new_item: @name is required')
        if not isinstance(ver, int):
            raise ValueError(f'Invalid object for new_item: @version {ver} is invalid')
        if path not in self.objs:
            self.objs[path] = {}
        self.objs[path][ver] = obj

    def initial_default(self):
        ver = 1
        self.new_item({
            '@type': 'a-scene',
            '@version': ver,
            '@name': '/root',
            '@id': 'root',
            '@children': {
                # -1 means latest version
                # Note: this makes the object mutable. I did this only for demo.
                'assets': -1,
                'ground': -1,
                'background': -1,
                'camera': -1,
            }
        })
        self.new_item({
            '@type': 'a-assets',
            '@version': ver,
            '@name': '/root/assets',
            '@id': 'assets',
            '@children': {
                'groundTexture': -1,
                'skyTexture': -1,
                'voxel': -1,
            }
        })
        self.new_item({
            '@type': 'img',
            '@version': ver,
            '@name': '/root/assets/groundTexture',
            '@id': 'groundTexture',
            '@children': {},
            'src': '/static/floor.jpg',
            'alt': ''
        })
        self.new_item({
            '@type': 'img',
            '@version': ver,
            '@name': '/root/assets/skyTexture',
            '@id': 'skyTexture',
            '@children': {},
            'src': '/static/sky.jpg',
            'alt': ''
        })
        self.new_item({
            '@type': 'a-mixin',
            '@version': ver,
            '@name': '/root/assets/voxel',
            '@id': 'voxel',
            '@children': {},
            'geometry': 'primitive: box; height: 0.5; width: 0.5; depth: 0.5',
            'material': 'shader: standard'
        })
        self.new_item({
            '@type': 'a-cylinder',
            '@version': ver,
            '@name': '/root/ground',
            '@id': 'voxel',
            '@children': {},
            'src': '#groundTexture',
            'radius': 32,
            'height': 0.1,
        })
        self.new_item({
            '@type': 'a-sky',
            '@id': 'background',
            '@version': ver,
            '@name': '/root/background',
            '@children': {},
            'src': '#skyTexture',
            'radius': 30,
            'theta-length': 90,
        })
        self.new_item({
            '@type': 'a-camera',
            '@id': 'camera',
            '@version': ver,
            '@name': '/root/camera',
            '@children': {
                'cursor': -1
            },
        })
        self.new_item({
            '@type': 'a-cursor',
            '@id': 'cursor',
            '@version': ver,
            '@name': '/root/camera/cursor',
            '@children': {},
            'intersection-spawn': 'event: click; offset: 0.25 0.25 0.25; snap: 0.5 0.5 0.5; mixin: voxel',
        })

    def patch_item(self, patch: dict[str, any]):
        name = patch.get('@name', '')
        if not name:
            raise ValueError(f'Invalid patch: @name is required')
        ver = patch.get('@version', -1)
        if not isinstance(ver, int) or ver < 0:
            raise ValueError(f'Invalid patch: @version is required')
        prev = patch.get('@prev', -1)
        op = patch.get('op', '')
        if op not in ['new', 'add', 'remove', 'replace', 'nop']:
            raise ValueError(f'Invalid patch: op is required')
        # The following code does not handle consensus problem
        # However, json patch can be modified to a CRDT
        if op == 'nop':
            pass
        elif op == 'new':
            obj = patch.get('value', {})
            if not obj:
                raise ValueError(f'Invalid patch: new: value is required')
            obj['@name'] = name
            obj['@version'] = ver
            obj['@id'] = name[name.rfind('/')+1:]
            if name not in self.objs:
                self.objs[name] = {}
            self.objs[name][ver] = obj
        else:
            origin = self.get_item(name)
            if not origin:
                raise KeyError(f'Invalid patch: object {name} not found')
            new_doc = jsonpatch.apply_patch(origin, [patch], False)
            new_doc['@version'] = ver
            self.objs[name][ver] = new_doc
        self.patch_lst.append(copy.deepcopy(patch))
