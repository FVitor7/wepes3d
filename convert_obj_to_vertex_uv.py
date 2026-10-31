def convert_obj_to_vertex_uv(input_path, output_path):
    vertices = []
    uvs = []
    faces = []

    # Ler OBJ
    with open(input_path, 'r') as f:
        for line in f:
            if line.startswith('v '):
                vertices.append(tuple(map(float, line.strip().split()[1:])))
            elif line.startswith('vt '):
                uvs.append(tuple(map(float, line.strip().split()[1:])))
            elif line.startswith('f '):
                face = []
                for part in line.strip().split()[1:]:
                    v_idx, vt_idx = part.split('/')[:2]
                    face.append((int(v_idx)-1, int(vt_idx)-1))
                faces.append(face)

    # Novo conjunto
    new_vertices = []
    new_uvs = []
    new_faces = []

    # Mapeamento (v, vt) → novo índice
    mapping = {}

    for face in faces:
        new_face = []
        for v_idx, vt_idx in face:
            key = (v_idx, vt_idx)

            if key not in mapping:
                new_index = len(new_vertices)
                mapping[key] = new_index

                new_vertices.append(vertices[v_idx])
                new_uvs.append(uvs[vt_idx])

            new_face.append(mapping[key])

        new_faces.append(new_face)

    # Escrever novo OBJ
    with open(output_path, 'w') as f:
        for v in new_vertices:
            f.write(f"v {v[0]} {v[1]} {v[2]}\n")

        for uv in new_uvs:
            f.write(f"vt {uv[0]} {uv[1]}\n")

        for face in new_faces:
            # agora v e vt têm MESMO índice
            f.write("f " + " ".join([f"{i+1}/{i+1}" for i in face]) + "\n")

    print("Conversão concluída!")

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Converter OBJ para formato vertex-uv")
    parser.add_argument("input", help="Caminho do arquivo OBJ de entrada")
    parser.add_argument("output", help="Caminho do arquivo OBJ de saída")

    args = parser.parse_args()

    convert_obj_to_vertex_uv(args.input, args.output)

if __name__ == "__main__":
    main()
