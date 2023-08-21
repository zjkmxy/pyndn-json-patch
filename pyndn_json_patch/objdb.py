import jsonpatch


class ObjDb:
    objs: dict[str, dict[int, any]]

    def __init__(self):
        self.objs = {}

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
                'theBox': -1,
                'theSphere': -1,
                'theCylinder': -1,
                'thePlane': -1,
                'theSky': -1,
            }
        })
        self.new_item({
            '@type': 'a-box',
            '@id': 'theBox',
            '@version': ver,
            '@name': '/root/theBox',
            '@children': {},
            'position': '-1 0.5 -3',
            'rotation': '0 45 0',
            'color': '#4CC3D9'
        })
        self.new_item({
            '@type': 'a-sphere',
            '@id': 'theSphere',
            '@version': ver,
            '@name': '/root/theSphere',
            '@children': {},
            'position': '0 1.25 -5',
            'radius': 1.25,
            'color': '#EF2D5E'
        })
        self.new_item({
            '@type': 'a-cylinder',
            '@id': 'theCylinder',
            '@version': ver,
            '@name': '/root/theCylinder',
            '@children': {},
            'position': '1 0.75 -3',
            'radius': 0.5,
            'height': 1.5,
            'color': '#FFC65D'
        })
        self.new_item({
            '@type': 'a-plane',
            '@id': 'thePlane',
            '@version': ver,
            '@name': '/root/thePlane',
            '@children': {},
            'position': '0 0 -4',
            'rotation': '-90 0 0',
            'width': 4,
            'height': 4,
            'color': '#7BC8A4'
        })
        self.new_item({
            '@type': 'a-sky',
            '@id': 'theSky',
            '@version': ver,
            '@name': '/root/theSky',
            '@children': {},
            'color': '#ECECEC'
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
        if op not in ['new', 'add', 'remove', 'replace']:
            raise ValueError(f'Invalid patch: op is required')
        # The following code does not handle consensus problem
        # However, json patch can be modified to a CRDT
        if op == 'new':
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
