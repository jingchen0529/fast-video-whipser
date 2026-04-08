import type { AuthPermission } from "@/types/api";

export interface PermissionTreeNode {
  key: string;
  label: string;
  children: PermissionTreeNode[];
  permission?: AuthPermission;
}

const sortNodes = (nodes: PermissionTreeNode[]) => {
  nodes.sort((a, b) => a.label.localeCompare(b.label, "zh-CN"));
  for (const node of nodes) {
    sortNodes(node.children);
  }
  return nodes;
};

export const buildPermissionTree = (items: AuthPermission[]) => {
  const tree = new Map<string, PermissionTreeNode>();

  for (const permission of items) {
    const groupRootKey = permission.group_name;
    if (!tree.has(groupRootKey)) {
      tree.set(groupRootKey, {
        key: groupRootKey,
        label: permission.group_name,
        children: [],
      });
    }

    const rootNode = tree.get(groupRootKey)!;
    const segments = permission.code.split(".");
    let currentChildren = rootNode.children;
    let path = groupRootKey;

    for (let index = 0; index < segments.length; index += 1) {
      const segment = segments[index];
      path = `${path}.${segment}`;
      const isLeaf = index === segments.length - 1;

      let node = currentChildren.find((item) => item.key === path);
      if (!node) {
        node = {
          key: path,
          label: segment,
          children: [],
          permission: isLeaf ? permission : undefined,
        };
        currentChildren.push(node);
      }

      if (isLeaf) {
        node.permission = permission;
      }

      currentChildren = node.children;
    }
  }

  return sortNodes([...tree.values()]);
};

export const collectPermissionCodes = (node: PermissionTreeNode): string[] => {
  if (node.permission) {
    return [node.permission.code];
  }

  return node.children.flatMap((child) => collectPermissionCodes(child));
};

export const resolveNodeCheckState = (
  node: PermissionTreeNode,
  selectedCodes: Set<string>,
): boolean | "indeterminate" => {
  const codes = collectPermissionCodes(node);
  const checkedCount = codes.filter((code) => selectedCodes.has(code)).length;

  if (checkedCount === 0) {
    return false;
  }
  if (checkedCount === codes.length) {
    return true;
  }
  return "indeterminate";
};
