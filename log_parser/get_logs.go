package main

import "context"
import "fmt"
import "io"
import "os"
import "io/ioutil"

import "storj.io/uplink"

func check(e error) {
    if e != nil {
        panic(e)
    }
}

func main() {

	top_dir := os.Args[1]
	storj_folder := os.Args[2]

	ctx := context.Background()

	if _, err := os.Stat(top_dir); os.IsNotExist(err) {
		err := os.Mkdir(top_dir, os.ModeDir)
		check(err)
	}

	if _, err := os.Stat(top_dir + "\\0"); os.IsNotExist(err) {
		err := os.Mkdir(top_dir + "\\0", os.ModeDir)
		check(err)
	}

	dat, err := ioutil.ReadFile("C:\\Windows\\System32\\uplink\\accessgrant.txt")
	check(err)

	access, err := uplink.ParseAccess(string(dat))
	check(err)

    project, err := uplink.OpenProject(ctx, access)
	check(err)

	objects := project.ListObjects(ctx, storj_folder, nil)
	n := 1
	for objects.Next() {
		item := objects.Item()

		if _, err := os.Stat(top_dir+"\\0\\"+item.Key); os.IsNotExist(err) {
			success := false

			for !success {
				fmt.Println("downloading", item.Key, n)

				object, err := project.DownloadObject(ctx, storj_folder, item.Key, nil)
				if err != nil {
					fmt.Println("error downloading", item.Key)
				}
				defer object.Close()

				destination, err := os.Create(top_dir+"\\0\\"+item.Key)
				check(err)
				defer destination.Close()

				_, err = io.Copy(destination, object)
				if err != nil {
					fmt.Println("copy error, redownloading ...")
					os.Remove(destination.Name())
				} else {
					success = true
				}
			}

		} else {
			fmt.Println("skipping", item.Key, n)
		}

		n++;

	}

	err = objects.Err(); 
	check(err)

	defer project.Close()
}