"""Build the official processor conversation from the two evaluator images."""

def conversation(views, prompt):
    content = []
    for label, image in views:
        content.extend([{"type": "text", "text": label}, {"type": "image", "image": image}])
    content.append({"type": "text", "text": prompt})
    return [{"role": "user", "content": content}]
