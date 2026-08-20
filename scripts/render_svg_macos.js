ObjC.import("AppKit");
ObjC.import("Foundation");

function text(value) {
  return ObjC.unwrap(value);
}

function run(argv) {
  if (argv.length !== 2) {
    throw new Error("AppKit renderer requires exactly one SVG input and one PNG output");
  }

  const input = $(argv[0]).stringByStandardizingPath;
  const output = $(argv[1]).stringByStandardizingPath;
  if (!input.hasPrefix("/") || !output.hasPrefix("/")) {
    throw new Error("AppKit renderer requires absolute paths");
  }
  if (text(input.pathExtension.lowercaseString) !== "svg") {
    throw new Error("AppKit renderer input must be an SVG file");
  }
  if (text(output.pathExtension.lowercaseString) !== "png") {
    throw new Error("AppKit renderer output must be a PNG file");
  }
  if (input.isEqualToString(output)) {
    throw new Error("AppKit renderer input and output must differ");
  }

  const manager = $.NSFileManager.defaultManager;
  if (!manager.fileExistsAtPath(input)) {
    throw new Error("AppKit renderer SVG input is unavailable");
  }
  const parent = output.stringByDeletingLastPathComponent;
  if (!manager.fileExistsAtPath(parent)) {
    throw new Error("AppKit renderer output directory is unavailable");
  }

  const image = $.NSImage.alloc.initWithContentsOfFile(input);
  if (!image || image.isNil() || image.size.width <= 0 || image.size.height <= 0) {
    throw new Error("AppKit could not decode the SVG input");
  }
  const representation = $.NSBitmapImageRep.imageRepWithData(image.TIFFRepresentation);
  if (!representation || representation.isNil()) {
    throw new Error("AppKit could not create a bitmap representation");
  }
  const png = representation.representationUsingTypeProperties(
    $.NSBitmapImageFileTypePNG,
    $({})
  );
  if (!png || png.isNil() || png.length <= 0) {
    throw new Error("AppKit could not encode PNG data");
  }

  const error = Ref();
  if (!png.writeToFileOptionsError(output, $.NSDataWritingAtomic, error)) {
    throw new Error("AppKit could not atomically publish the PNG output");
  }
  return "appkit";
}
